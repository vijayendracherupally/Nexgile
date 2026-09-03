"""Supplier engagement services (FR-3.C)."""
from __future__ import annotations

import math
import secrets
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import SubmissionStatus
from app.domain.models import (
    Bid, Campaign, Emission, ProcurementDecision, Scorecard, Submission, Supplier,
    SupplierInvitation,
)

MATURITY_BANDS = [
    (85, "leader"), (70, "advanced"), (55, "progressing"), (35, "developing"), (0, "beginner"),
]


def maturity_for(score: float) -> str:
    for threshold, label in MATURITY_BANDS:
        if score >= threshold:
            return label
    return "beginner"


def supplier_emissions(db: Session, supplier_id: int, year: int) -> float:
    """Scope 3 kgCO2e attributed to a supplier in a year."""
    total = db.scalar(
        select(func.coalesce(func.sum(Emission.co2e_kg), 0.0))
        .where(Emission.supplier_id == supplier_id, Emission.year == year,
               Emission.scenario_id.is_(None))
    )
    return float(total or 0.0)


def compute_scorecard(db: Session, supplier: Supplier, year: int) -> Scorecard:
    """FR-3.C.3 - disclosure, performance, data quality and target sub-scores."""
    submissions = db.scalars(
        select(Submission).where(Submission.supplier_id == supplier.id,
                                 Submission.reporting_year == year)
    ).all()
    latest = max(submissions, key=lambda s: s.updated_at, default=None)

    # Disclosure: did they respond, completely, and attest to it?
    disclosure = 0.0
    if latest:
        disclosure = latest.completeness_pct * 0.7
        if latest.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.VALIDATED,
                             SubmissionStatus.ATTESTED):
            disclosure += 15
        if latest.attested:
            disclosure += 15
    disclosure = min(100.0, disclosure)

    answers = (latest.answers if latest else {}) or {}

    def num(key: str, default: float = 0.0) -> float:
        try:
            return float(answers.get(key, default))
        except (TypeError, ValueError):
            return default

    # Performance: emissions intensity vs. spend, plus reduction achieved.
    emissions_kg = supplier_emissions(db, supplier.id, year)
    intensity = (emissions_kg / supplier.annual_spend) if supplier.annual_spend else 0.0
    prior = db.scalars(
        select(Scorecard).where(Scorecard.supplier_id == supplier.id,
                                Scorecard.period_year == year - 1)
    ).first()
    reduction_pct = num("reduction_achieved_pct", 0.0)
    performance = max(0.0, min(100.0, 50 + reduction_pct * 2 - intensity * 50))

    # Data quality: primary data beats estimates.
    channel_score = {"api": 100, "form": 80, "mobile": 75, "ocr": 60}.get(
        latest.capture_channel if latest else "", 30)
    validation_penalty = 10 * len(latest.validation_errors) if latest else 30
    data_quality = max(0.0, min(100.0, channel_score - validation_penalty))

    # Targets: does the supplier have credible targets of its own?
    target_score = 0.0
    if answers.get("has_reduction_target"):
        target_score += 40
    if answers.get("sbti_committed"):
        target_score += 30
    if answers.get("scope3_measured"):
        target_score += 30
    target_score = min(100.0, target_score)

    overall = round(
        disclosure * 0.30 + performance * 0.30 + data_quality * 0.20 + target_score * 0.20, 2)

    card = db.scalars(
        select(Scorecard).where(Scorecard.supplier_id == supplier.id,
                                Scorecard.period_year == year)
    ).first()
    if card is None:
        card = Scorecard(supplier_id=supplier.id, period_year=year)
        db.add(card)

    card.overall_score = overall
    card.disclosure_score = round(disclosure, 2)
    card.performance_score = round(performance, 2)
    card.data_quality_score = round(data_quality, 2)
    card.target_score = round(target_score, 2)
    card.maturity_level = maturity_for(overall)
    card.emissions_tco2e = round(emissions_kg / 1000, 3)
    card.emission_intensity = round(intensity, 6)
    card.yoy_delta = round(overall - prior.overall_score, 2) if prior else 0.0
    card.details = {
        "weights": {"disclosure": 0.30, "performance": 0.30,
                    "data_quality": 0.20, "targets": 0.20},
        "submission_status": latest.status if latest else "none",
        "capture_channel": latest.capture_channel if latest else None,
        "validation_error_count": len(latest.validation_errors) if latest else None,
        "reduction_achieved_pct": reduction_pct,
        "annual_spend": supplier.annual_spend,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    db.flush()
    return card


def rank_scorecards(db: Session, year: int, organization_id: int | None = None) -> list[Scorecard]:
    """FR-3.C.3 - overall and within-category rankings."""
    stmt = select(Scorecard).where(Scorecard.period_year == year)
    cards = list(db.scalars(stmt))
    suppliers = {s.id: s for s in db.scalars(select(Supplier))}
    if organization_id:
        cards = [c for c in cards
                 if suppliers.get(c.supplier_id)
                 and suppliers[c.supplier_id].organization_id == organization_id]

    for rank, card in enumerate(sorted(cards, key=lambda c: c.overall_score, reverse=True), 1):
        card.rank = rank

    by_category: dict[str, list[Scorecard]] = {}
    for card in cards:
        sup = suppliers.get(card.supplier_id)
        by_category.setdefault(sup.category if sup else "", []).append(card)
    for group in by_category.values():
        for rank, card in enumerate(sorted(group, key=lambda c: c.overall_score, reverse=True), 1):
            card.category_rank = rank
    db.flush()
    return cards


def build_network(db: Session, organization_id: int, year: int) -> dict:
    """FR-3.C.4 - multi-tier network map with hotspots and outliers."""
    suppliers = list(db.scalars(
        select(Supplier).where(Supplier.organization_id == organization_id)))
    nodes, edges = [], []
    tier_totals: dict[int, float] = {}
    country_totals: dict[str, dict] = {}
    category_totals: dict[str, dict] = {}

    for s in suppliers:
        kg = supplier_emissions(db, s.id, year)
        tier_totals[s.tier] = tier_totals.get(s.tier, 0.0) + kg
        nodes.append({
            "id": s.id, "name": s.name, "tier": s.tier, "category": s.category,
            "country": s.country, "latitude": s.latitude, "longitude": s.longitude,
            "annual_spend": s.annual_spend, "tco2e": round(kg / 1000, 3),
            "is_critical": s.is_critical, "risk_rating": s.risk_rating,
            "onboarding_status": s.onboarding_status,
            "parent_supplier_id": s.parent_supplier_id,
        })
        if s.parent_supplier_id:
            edges.append({"source": s.id, "target": s.parent_supplier_id,
                          "tier_step": f"T{s.tier}->T{max(1, s.tier - 1)}"})
        c = country_totals.setdefault(s.country or "??", {
            "country": s.country or "??", "tco2e": 0.0, "supplier_count": 0, "spend": 0.0})
        c["tco2e"] += kg / 1000
        c["supplier_count"] += 1
        c["spend"] += s.annual_spend or 0.0
        cat = category_totals.setdefault(s.category or "uncategorized", {
            "category": s.category or "uncategorized", "tco2e": 0.0,
            "supplier_count": 0, "spend": 0.0})
        cat["tco2e"] += kg / 1000
        cat["supplier_count"] += 1
        cat["spend"] += s.annual_spend or 0.0

    # Outliers: emission intensity more than 2 standard deviations from the mean.
    intensities = [
        (n["id"], n["name"], n["tco2e"] / n["annual_spend"] * 1_000_000)
        for n in nodes if n["annual_spend"]
    ]
    outliers = []
    if len(intensities) > 2:
        values = [i[2] for i in intensities]
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        for sid, name, value in intensities:
            z = (value - mean) / sd if sd else 0.0
            if abs(z) >= 2:
                outliers.append({
                    "supplier_id": sid, "name": name,
                    "intensity_tco2e_per_m_spend": round(value, 3),
                    "peer_mean": round(mean, 3), "z_score": round(z, 2),
                    "direction": "high" if z > 0 else "low",
                })

    total_t = sum(n["tco2e"] for n in nodes)
    hotspots = sorted(nodes, key=lambda n: n["tco2e"], reverse=True)[:15]
    for h in hotspots:
        h["share_pct"] = round(h["tco2e"] / total_t * 100, 2) if total_t else 0.0

    return {
        "year": year,
        "supplier_count": len(suppliers),
        "total_tco2e": round(total_t, 3),
        "tiers": [
            {"tier": t, "tco2e": round(v / 1000, 3),
             "supplier_count": sum(1 for n in nodes if n["tier"] == t)}
            for t, v in sorted(tier_totals.items())
        ],
        "nodes": nodes,
        "edges": edges,
        "geographic_heatmap": sorted(
            [{**c, "tco2e": round(c["tco2e"], 3)} for c in country_totals.values()],
            key=lambda c: c["tco2e"], reverse=True),
        "category_hotspots": sorted(
            [{**c, "tco2e": round(c["tco2e"], 3),
              "share_pct": round(c["tco2e"] / total_t * 100, 2) if total_t else 0.0}
             for c in category_totals.values()],
            key=lambda c: c["tco2e"], reverse=True),
        "supplier_hotspots": hotspots,
        "outliers": outliers,
    }


def resilience_scenarios(db: Session, organization_id: int, year: int) -> list[dict]:
    """FR-3.C.4 - alternative sourcing and resilience/emissions scenarios."""
    network = build_network(db, organization_id, year)
    hotspots = network["supplier_hotspots"][:5]
    scenarios = []
    for h in hotspots:
        alternatives = [
            n for n in network["nodes"]
            if n["category"] == h["category"] and n["id"] != h["id"] and n["tco2e"] > 0
        ]
        alternatives.sort(key=lambda n: n["tco2e"] / max(n["annual_spend"], 1))
        best = alternatives[0] if alternatives else None
        if best and h["annual_spend"]:
            best_intensity = best["tco2e"] / max(best["annual_spend"], 1)
            projected = best_intensity * h["annual_spend"]
            delta = projected - h["tco2e"]
        else:
            projected, delta = h["tco2e"], 0.0
        scenarios.append({
            "scenario": f"Re-source '{h['name']}' within {h['category'] or 'category'}",
            "current_supplier": h["name"],
            "current_tco2e": h["tco2e"],
            "current_country": h["country"],
            "alternative_supplier": best["name"] if best else None,
            "alternative_country": best["country"] if best else None,
            "projected_tco2e": round(projected, 3),
            "delta_tco2e": round(delta, 3),
            "single_source_risk": h["is_critical"],
            "concentration_pct": h.get("share_pct", 0.0),
            "note": (
                "Illustrative resilience scenario. It never alters actuals (FR-7.8); "
                "promote it to a Scenario to model it formally."
            ),
        })
    return scenarios


def score_bids(db: Session, decision: ProcurementDecision) -> list[Bid]:
    """FR-3.C.5 - carbon-weighted bids and carbon-inclusive TCO."""
    bids = list(db.scalars(select(Bid).where(Bid.decision_id == decision.id)))
    if not bids:
        return []
    price_of_carbon = decision.internal_carbon_price or 0.0

    for b in bids:
        lifetime = max(b.lifetime_years or 1.0, 1.0)
        total_carbon_kg = (
            (b.embodied_kgco2e_per_unit + b.logistics_kgco2e_per_unit) * b.quantity
            + b.annual_operating_kgco2e * lifetime
        )
        financial_tco = b.price * b.quantity + b.annual_operating_cost * lifetime
        b.carbon_cost = round(total_carbon_kg / 1000 * price_of_carbon, 2)
        b.carbon_inclusive_tco = round(financial_tco + b.carbon_cost, 2)

    max_tco = max(b.carbon_inclusive_tco for b in bids) or 1.0
    min_tco = min(b.carbon_inclusive_tco for b in bids)
    max_carbon = max(
        (b.embodied_kgco2e_per_unit + b.logistics_kgco2e_per_unit) * b.quantity
        + b.annual_operating_kgco2e * max(b.lifetime_years or 1.0, 1.0) for b in bids) or 1.0

    carbon_weight = (decision.carbon_weight_pct or 0.0) / 100.0
    for b in bids:
        carbon_kg = ((b.embodied_kgco2e_per_unit + b.logistics_kgco2e_per_unit) * b.quantity
                     + b.annual_operating_kgco2e * max(b.lifetime_years or 1.0, 1.0))
        cost_score = 100 * (1 - (b.carbon_inclusive_tco - min_tco) / (max_tco - min_tco)) \
            if max_tco > min_tco else 100.0
        carbon_score = 100 * (1 - carbon_kg / max_carbon) if max_carbon else 100.0
        quality_weight = max(0.0, 1.0 - carbon_weight - 0.4)
        b.weighted_score = round(
            cost_score * 0.4 + carbon_score * carbon_weight + b.quality_score * quality_weight, 2)

    for rank, b in enumerate(sorted(bids, key=lambda x: x.weighted_score, reverse=True), 1):
        b.rank = rank
    db.flush()
    return bids


def new_access_token() -> str:
    return secrets.token_urlsafe(24)


def campaign_progress(db: Session, campaign: Campaign) -> dict:
    """FR-3.C.1 - invitations, reminders, progress tracking."""
    invites = list(db.scalars(
        select(SupplierInvitation).where(SupplierInvitation.campaign_id == campaign.id)))
    submissions = {
        s.supplier_id: s for s in db.scalars(
            select(Submission).where(Submission.campaign_id == campaign.id))
    }
    by_status: dict[str, int] = {}
    for inv in invites:
        sub = submissions.get(inv.supplier_id)
        status = sub.status if sub else inv.status
        by_status[status] = by_status.get(status, 0) + 1
    responded = sum(
        1 for s in submissions.values()
        if s.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.VALIDATED,
                        SubmissionStatus.ATTESTED)
    )
    days_left = (campaign.due_date - date.today()).days if campaign.due_date else None
    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "due_date": campaign.due_date.isoformat() if campaign.due_date else None,
        "days_remaining": days_left,
        "is_overdue": days_left is not None and days_left < 0,
        "invited": len(invites),
        "responded": responded,
        "response_rate_pct": round(responded / len(invites) * 100, 1) if invites else 0.0,
        "average_progress_pct": round(
            sum(i.progress_pct for i in invites) / len(invites), 1) if invites else 0.0,
        "reminders_sent": sum(i.reminders_sent for i in invites),
        "by_status": by_status,
        "languages_used": sorted({i.language for i in invites}),
    }


def extract_from_document(text: str) -> dict:
    """FR-3.C.2 / FR-3.D.1 - document/OCR field extraction.

    A deterministic keyword extractor stands in for the OCR/ML service so the
    workflow is exercisable end to end. Swap the body for your provider.
    """
    import re
    fields: dict = {}
    patterns = {
        "total_kwh": r"(\d[\d,.]*)\s*(?:kwh|kilowatt[- ]hours?)",
        "total_amount": r"(?:total|amount due|sum)\D{0,12}([\d,.]+)",
        "invoice_number": r"(?:invoice|inv)[\s#:]*([A-Z0-9-]{4,})",
        "period_start": r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|until)",
        "period_end": r"(?:to|-|until)\s*(\d{4}-\d{2}-\d{2})",
        "co2e_tonnes": r"([\d,.]+)\s*(?:t|tonnes?|metric tons?)\s*co2e",
        "gas_m3": r"(\d[\d,.]*)\s*m3\s*(?:natural )?gas",
        "litres": r"(\d[\d,.]*)\s*(?:l|litres?|liters?)\b",
    }
    lowered = text.lower()
    for key, pattern in patterns.items():
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            raw = match.group(1)
            try:
                fields[key] = float(raw.replace(",", ""))
            except ValueError:
                fields[key] = raw.upper()
    currency = re.search(r"\b(EUR|USD|GBP|CHF|SEK|PLN)\b", text, re.IGNORECASE)
    if currency:
        fields["currency"] = currency.group(1).upper()
    return {
        "extracted_fields": fields,
        "field_count": len(fields),
        "confidence": round(min(0.95, 0.35 + 0.09 * len(fields)), 2),
        "requires_review": len(fields) < 3,
        "extractor": "keyword-rules-v1",
    }


def validate_submission(questionnaire_questions: list[dict], answers: dict) -> list[dict]:
    """FR-3.C.2 - validations before a submission is accepted."""
    errors: list[dict] = []
    for question in questionnaire_questions:
        code = question.get("code")
        value = answers.get(code)
        if question.get("required") and (value is None or value == ""):
            errors.append({"code": code, "message": "Required answer is missing",
                           "severity": "error"})
            continue
        if value in (None, ""):
            continue
        qtype = question.get("type", "text")
        if qtype == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors.append({"code": code, "message": "Expected a number",
                               "severity": "error"})
                continue
            if "min" in question and number < question["min"]:
                errors.append({"code": code,
                               "message": f"Below minimum {question['min']}",
                               "severity": "error"})
            if "max" in question and number > question["max"]:
                errors.append({"code": code,
                               "message": f"Above maximum {question['max']}",
                               "severity": "warning"})
        elif qtype == "choice" and question.get("options"):
            if value not in question["options"]:
                errors.append({"code": code,
                               "message": f"Must be one of {question['options']}",
                               "severity": "error"})
        if question.get("evidence_required") and not answers.get(f"{code}__evidence"):
            errors.append({"code": code, "message": "Supporting evidence is required",
                           "severity": "warning"})
    return errors


def completeness_of(questions: list[dict], answers: dict) -> float:
    if not questions:
        return 0.0
    answered = sum(1 for q in questions
                   if answers.get(q.get("code")) not in (None, "", []))
    return round(answered / len(questions) * 100, 1)
