"""AI analytics and reduction planning (FR-3.D)."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import SCOPE3_CATEGORIES, DataOrigin, Scope
from app.domain.models import (
    ActivityData, Anomaly, Calculation, Category, DataGap, Emission, Entity,
    Facility, InternalCarbonPrice, ReductionInitiative, Scenario, Supplier, Target,
    Transaction,
)
from app.engine import uncertainty as unc_engine

# ---------------------------------------------------------------------------
# FR-3.D.1  Automated spend categorization
# ---------------------------------------------------------------------------

# Keyword -> Scope 3 category number. Ordered: the first match wins.
SPEND_RULES: list[tuple[tuple[str, ...], int]] = [
    (("flight", "airline", "air travel", "hotel", "rail ticket", "taxi", "per diem"), 6),
    (("commut", "employee travel", "shuttle", "parking permit"), 7),
    (("freight", "haulage", "courier", "shipping", "logistics", "forwarding"), 4),
    (("waste", "recycl", "landfill", "effluent", "scrap disposal"), 5),
    (("machine", "equipment", "plant", "capital", "vehicle purchase", "building works"), 2),
    (("fuel", "diesel", "petrol", "gas supply", "electricity network", "transmission"), 3),
    (("lease", "rental", "tenancy", "warehouse rent"), 8),
    (("franchise",), 14),
    (("investment", "equity stake", "bond", "fund"), 15),
    (("steel", "aluminium", "aluminum", "polymer", "resin", "component", "raw material",
      "chemical", "packaging", "consult", "software", "service", "maintenance",
      "cleaning", "catering", "office"), 1),
]


def categorize_spend(description: str, gl_account: str = "") -> tuple[int | None, float, str]:
    """Return (category_number, confidence, method)."""
    text = f"{description} {gl_account}".lower()
    for keywords, number in SPEND_RULES:
        for kw in keywords:
            if kw in text:
                # Longer, more distinctive keywords earn more confidence.
                confidence = min(0.96, 0.55 + 0.03 * len(kw.split()) + 0.02 * (len(kw) / 5))
                return number, round(confidence, 2), f"rule:{kw}"
    return None, 0.0, "unmatched"


def run_spend_categorization(db: Session, *, entity_id: int | None = None,
                             limit: int = 5000) -> dict:
    stmt = select(Transaction).where(Transaction.category_id.is_(None))
    if entity_id:
        stmt = stmt.where(Transaction.entity_id == entity_id)
    transactions = list(db.scalars(stmt.limit(limit)))
    categories = {
        c.number: c for c in db.scalars(
            select(Category).where(Category.scope == Scope.SCOPE_3))
    }
    matched, unmatched = 0, 0
    by_category: dict[str, dict] = {}
    for t in transactions:
        number, confidence, method = categorize_spend(t.description, t.gl_account)
        if number is None or number not in categories:
            unmatched += 1
            continue
        cat = categories[number]
        t.category_id = cat.id
        t.categorization_confidence = confidence
        t.categorized_by = "ai" if confidence >= 0.7 else "rule"
        matched += 1
        agg = by_category.setdefault(cat.name, {
            "category_number": number, "category": cat.name,
            "transaction_count": 0, "amount": 0.0, "avg_confidence": 0.0})
        agg["transaction_count"] += 1
        agg["amount"] += t.amount
        agg["avg_confidence"] += confidence
    for agg in by_category.values():
        agg["avg_confidence"] = round(agg["avg_confidence"] / agg["transaction_count"], 3)
        agg["amount"] = round(agg["amount"], 2)
    db.flush()
    return {
        "examined": len(transactions),
        "categorized": matched,
        "unmatched": unmatched,
        "coverage_pct": round(matched / len(transactions) * 100, 1) if transactions else 0.0,
        "requires_human_review": sum(
            1 for t in transactions
            if t.categorization_confidence and t.categorization_confidence < 0.7),
        "by_category": sorted(by_category.values(), key=lambda d: -d["amount"]),
    }


# ---------------------------------------------------------------------------
# FR-3.D.1  Anomaly detection
# ---------------------------------------------------------------------------

def detect_anomalies(db: Session, *, entity_id: int | None = None,
                     z_threshold: float = 2.0, persist: bool = True) -> list[dict]:
    """Flags spikes, drops, outliers, duplicates and unit mismatches."""
    stmt = select(Emission).where(Emission.scenario_id.is_(None))
    if entity_id:
        stmt = stmt.where(Emission.entity_id == entity_id)
    emissions = list(db.scalars(stmt))

    groups: dict[tuple, list[Emission]] = defaultdict(list)
    for e in emissions:
        groups[(e.entity_id, e.facility_id, e.scope, e.category_id)].append(e)

    found: list[dict] = []
    for key, series in groups.items():
        if len(series) < 4:
            continue
        values = [e.co2e_kg for e in series]
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        if sd == 0:
            continue
        for e in series:
            z = (e.co2e_kg - mean) / sd
            if abs(z) < z_threshold:
                continue
            entity = db.get(Entity, e.entity_id)
            facility = db.get(Facility, e.facility_id) if e.facility_id else None
            kind = "spike" if z > 0 else "drop"
            record = {
                "entity_id": e.entity_id,
                "entity_name": entity.name if entity else None,
                "facility_name": facility.name if facility else None,
                "object_type": "emission", "object_id": e.id,
                "scope": e.scope, "year": e.year,
                "anomaly_type": kind,
                "severity": "high" if abs(z) >= 3 else "medium",
                "observed_value": round(e.co2e_kg, 3),
                "expected_value": round(mean, 3),
                "deviation_pct": round((e.co2e_kg - mean) / mean * 100, 2) if mean else 0.0,
                "z_score": round(z, 2),
                "explanation": (
                    f"{kind.title()} of {abs(z):.1f} standard deviations against the "
                    f"{len(series)}-period mean for this entity/facility/scope/category."
                ),
            }
            found.append(record)
            if persist:
                exists = db.scalars(select(Anomaly).where(
                    Anomaly.object_type == "emission", Anomaly.object_id == e.id)).first()
                if exists is None:
                    db.add(Anomaly(
                        entity_id=e.entity_id, object_type="emission", object_id=e.id,
                        anomaly_type=kind, severity=record["severity"],
                        observed_value=e.co2e_kg, expected_value=mean,
                        deviation_pct=record["deviation_pct"], z_score=z,
                        explanation=record["explanation"],
                    ))

    # Duplicates: same entity, key, period and quantity.
    seen: dict[tuple, int] = {}
    for a in db.scalars(select(ActivityData).where(ActivityData.scenario_id.is_(None))):
        key = (a.entity_id, a.facility_id, a.activity_key, a.period_start, round(a.quantity, 6))
        if key in seen:
            found.append({
                "entity_id": a.entity_id, "object_type": "activity_data", "object_id": a.id,
                "anomaly_type": "duplicate", "severity": "medium",
                "observed_value": a.quantity, "expected_value": a.quantity,
                "deviation_pct": 0.0, "z_score": 0.0,
                "explanation": f"Identical to activity data #{seen[key]} "
                               f"(same source, period and quantity).",
            })
            if persist and db.scalars(select(Anomaly).where(
                    Anomaly.object_type == "activity_data",
                    Anomaly.object_id == a.id)).first() is None:
                db.add(Anomaly(
                    entity_id=a.entity_id, object_type="activity_data", object_id=a.id,
                    anomaly_type="duplicate", severity="medium",
                    observed_value=a.quantity, expected_value=a.quantity,
                    explanation=f"Duplicate of activity data #{seen[key]}",
                ))
        else:
            seen[key] = a.id

    if persist:
        db.flush()
    return sorted(found, key=lambda r: abs(r.get("z_score", 0)), reverse=True)


# ---------------------------------------------------------------------------
# FR-3.D.1 / FR-7.4  Gap identification and estimation
# ---------------------------------------------------------------------------

def identify_gaps(db: Session, *, entity_id: int, year: int,
                  persist: bool = True) -> list[dict]:
    """Every facility is expected to report each month for Scope 1 and 2, and
    every Scope 3 category is expected to be present."""
    facilities = list(db.scalars(select(Facility).where(Facility.entity_id == entity_id)))
    gaps: list[dict] = []

    present: set[tuple] = set()
    for a in db.scalars(select(ActivityData).where(
        ActivityData.entity_id == entity_id,
        ActivityData.period_start >= date(year, 1, 1),
        ActivityData.period_start <= date(year, 12, 31),
        ActivityData.scenario_id.is_(None),
    )):
        present.add((a.facility_id, a.scope, a.period_start.month))

    for facility in facilities:
        for scope in (Scope.SCOPE_1, Scope.SCOPE_2):
            missing_months = [m for m in range(1, 13)
                              if (facility.id, scope, m) not in present]
            if not missing_months:
                continue
            # Estimate the gap from the facility's own reported average.
            reported = [
                e.co2e_kg for e in db.scalars(select(Emission).where(
                    Emission.facility_id == facility.id, Emission.scope == scope,
                    Emission.year == year, Emission.scenario_id.is_(None)))
            ]
            monthly_avg = (sum(reported) / len(reported)) if reported else 0.0
            estimate = monthly_avg * len(missing_months)
            gaps.append({
                "entity_id": entity_id, "facility_id": facility.id,
                "facility_name": facility.name, "scope": scope,
                "period_year": year,
                "period_label": ", ".join(
                    date(year, m, 1).strftime("%b") for m in missing_months),
                "gap_type": "missing_activity",
                "missing_months": len(missing_months),
                "description": f"{len(missing_months)} month(s) of {scope} data missing "
                               f"for {facility.name}",
                "estimated_co2e_kg": round(estimate, 3),
                "estimation_method": "facility monthly average x missing months"
                if reported else "no basis - facility has never reported",
                "status": "open",
            })

    reported_categories = {
        e.category_id for e in db.scalars(select(Emission).where(
            Emission.entity_id == entity_id, Emission.year == year,
            Emission.scope == Scope.SCOPE_3, Emission.scenario_id.is_(None)))
    }
    categories = {c.number: c for c in db.scalars(
        select(Category).where(Category.scope == Scope.SCOPE_3))}
    for number, name in SCOPE3_CATEGORIES.items():
        cat = categories.get(number)
        if cat and cat.id not in reported_categories:
            gaps.append({
                "entity_id": entity_id, "facility_id": None, "scope": Scope.SCOPE_3,
                "category_id": cat.id, "category_number": number,
                "period_year": year, "period_label": str(year),
                "gap_type": "missing_scope3_category",
                "description": f"Scope 3 category {number} ({name}) is not reported",
                "estimated_co2e_kg": 0.0,
                "estimation_method": "screening estimate required",
                "status": "open",
            })

    if persist:
        for g in gaps:
            exists = db.scalars(select(DataGap).where(
                DataGap.entity_id == entity_id, DataGap.period_year == year,
                DataGap.facility_id == g.get("facility_id"),
                DataGap.scope == g["scope"],
                DataGap.gap_type == g["gap_type"])).first()
            if exists is None:
                db.add(DataGap(
                    entity_id=entity_id, facility_id=g.get("facility_id"),
                    scope=g["scope"], category_id=g.get("category_id"),
                    period_year=year, period_label=g["period_label"],
                    gap_type=g["gap_type"], description=g["description"],
                    estimated_co2e_kg=g["estimated_co2e_kg"],
                    estimation_method=g["estimation_method"],
                ))
        db.flush()
    return gaps


# ---------------------------------------------------------------------------
# FR-3.D.1  Predictive forecasting
# ---------------------------------------------------------------------------

def forecast(db: Session, *, entity_id: int, horizon_years: int = 5,
             scope: str | None = None) -> dict:
    """Ordinary least squares on the annual series, with a confidence band."""
    stmt = select(Emission.year, func.sum(Emission.co2e_kg)).where(
        Emission.entity_id == entity_id, Emission.scenario_id.is_(None))
    if scope:
        stmt = stmt.where(Emission.scope == scope)
    history = db.execute(stmt.group_by(Emission.year).order_by(Emission.year)).all()
    series = [{"year": int(r[0]), "tco2e": round(float(r[1]) / 1000, 3)} for r in history]

    if len(series) < 2:
        return {
            "entity_id": entity_id, "scope": scope, "history": series,
            "projection": [], "method": "insufficient_history",
            "note": "At least two reported years are required to project a trend.",
        }

    xs = [s["year"] for s in series]
    ys = [s["tco2e"] for s in series]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom if denom else 0.0
    intercept = mean_y - slope * mean_x

    residuals = [ys[i] - (intercept + slope * xs[i]) for i in range(n)]
    rss = sum(r ** 2 for r in residuals)
    tss = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1 - rss / tss if tss else 0.0
    std_err = math.sqrt(rss / max(1, n - 2))

    last_year = max(xs)
    projection = []
    for i in range(1, horizon_years + 1):
        year = last_year + i
        value = intercept + slope * year
        # The band widens as we extrapolate.
        band = 1.96 * std_err * math.sqrt(1 + i / n)
        projection.append({
            "year": year,
            "tco2e": round(max(0.0, value), 3),
            "low": round(max(0.0, value - band), 3),
            "high": round(max(0.0, value + band), 3),
        })

    return {
        "entity_id": entity_id, "scope": scope,
        "history": series,
        "projection": projection,
        "method": "ordinary_least_squares",
        "annual_trend_tco2e": round(slope, 3),
        "annual_trend_pct": round(slope / mean_y * 100, 2) if mean_y else 0.0,
        "r_squared": round(r_squared, 4),
        "std_error": round(std_err, 3),
        "confidence": "high" if r_squared >= 0.8 else
                      "medium" if r_squared >= 0.5 else "low",
    }


# ---------------------------------------------------------------------------
# FR-3.D.3  Hotspots, levers, MACC, roadmap, ROI
# ---------------------------------------------------------------------------

def pareto_hotspots(db: Session, *, entity_id: int | None = None, year: int | None = None,
                    dimension: str = "category") -> dict:
    """Pareto analysis: which few sources carry most of the footprint."""
    stmt = select(Emission).where(Emission.scenario_id.is_(None))
    if entity_id:
        stmt = stmt.where(Emission.entity_id == entity_id)
    if year:
        stmt = stmt.where(Emission.year == year)
    emissions = list(db.scalars(stmt))

    buckets: dict[str, float] = defaultdict(float)
    for e in emissions:
        if dimension == "category":
            cat = db.get(Category, e.category_id) if e.category_id else None
            key = cat.name if cat else f"{e.scope} (uncategorized)"
        elif dimension == "facility":
            fac = db.get(Facility, e.facility_id) if e.facility_id else None
            key = fac.name if fac else "Unassigned facility"
        elif dimension == "supplier":
            sup = db.get(Supplier, e.supplier_id) if e.supplier_id else None
            key = sup.name if sup else "No supplier"
        elif dimension == "scope":
            key = e.scope
        else:
            ent = db.get(Entity, e.entity_id)
            key = ent.name if ent else str(e.entity_id)
        buckets[key] += e.co2e_kg

    total = sum(buckets.values())
    ordered = sorted(buckets.items(), key=lambda kv: -kv[1])
    items, cumulative = [], 0.0
    vital_few = 0
    for name, kg in ordered:
        cumulative += kg
        cum_pct = cumulative / total * 100 if total else 0.0
        if cum_pct <= 80.0:
            vital_few += 1
        items.append({
            "name": name,
            "tco2e": round(kg / 1000, 3),
            "share_pct": round(kg / total * 100, 2) if total else 0.0,
            "cumulative_pct": round(cum_pct, 2),
            "in_vital_few": cum_pct <= 80.0,
        })
    return {
        "dimension": dimension, "year": year, "entity_id": entity_id,
        "total_tco2e": round(total / 1000, 3),
        "items": items,
        "vital_few_count": max(1, vital_few),
        "vital_few_share_pct": round(
            sum(i["share_pct"] for i in items[:max(1, vital_few)]), 2),
        "interpretation": (
            f"{max(1, vital_few)} of {len(items)} {dimension} groups account for "
            f"roughly 80% of the footprint - target these first."
        ) if items else "No emissions in scope.",
    }


def build_macc(db: Session, *, entity_id: int | None = None,
               scenario_id: int | None = None) -> dict:
    """FR-3.D.3 - marginal abatement cost curve with investment priority."""
    stmt = select(ReductionInitiative)
    stmt = stmt.where(ReductionInitiative.scenario_id.is_(None) if scenario_id is None
                      else ReductionInitiative.scenario_id == scenario_id)
    if entity_id:
        stmt = stmt.where(ReductionInitiative.entity_id == entity_id)
    initiatives = list(db.scalars(stmt))

    computed = []
    for i in initiatives:
        lifetime = max(1, i.lifetime_years or 1)
        lifetime_abatement = (i.annual_abatement_tco2e or 0.0) * lifetime
        net_cost = (i.capex or 0.0) + (i.annual_opex_delta or 0.0) * lifetime
        mac = net_cost / lifetime_abatement if lifetime_abatement else 0.0
        annual_saving = -(i.annual_opex_delta or 0.0)
        payback = (i.capex / annual_saving) if annual_saving > 0 and i.capex else 0.0
        roi = ((annual_saving * lifetime - (i.capex or 0.0)) / i.capex * 100) \
            if i.capex else 0.0
        i.marginal_abatement_cost = round(mac, 2)
        i.payback_years = round(payback, 2)
        i.roi_pct = round(roi, 2)
        computed.append({
            "id": i.id, "name": i.name, "lever_category": i.lever_category,
            "scope": i.scope, "status": i.status,
            "annual_abatement_tco2e": round(i.annual_abatement_tco2e or 0.0, 3),
            "lifetime_abatement_tco2e": round(lifetime_abatement, 3),
            "capex": i.capex, "annual_opex_delta": i.annual_opex_delta,
            "lifetime_years": lifetime,
            "marginal_abatement_cost": round(mac, 2),
            "payback_years": round(payback, 2),
            "roi_pct": round(roi, 2),
            "technology_readiness": i.technology_readiness,
            "start_year": i.start_year, "end_year": i.end_year,
            "progress_pct": i.progress_pct,
            "realized_abatement_tco2e": i.realized_abatement_tco2e,
            "is_negative_cost": mac < 0,
        })

    computed.sort(key=lambda c: c["marginal_abatement_cost"])
    cumulative = 0.0
    for rank, c in enumerate(computed, 1):
        c["investment_priority"] = rank
        c["cumulative_abatement_tco2e"] = round(
            cumulative + c["annual_abatement_tco2e"], 3)
        cumulative += c["annual_abatement_tco2e"]
        init = db.get(ReductionInitiative, c["id"])
        if init:
            init.investment_priority = rank
    db.flush()

    return {
        "entity_id": entity_id, "scenario_id": scenario_id,
        "curve": computed,
        "total_annual_abatement_tco2e": round(cumulative, 3),
        "total_capex": round(sum(c["capex"] or 0 for c in computed), 2),
        "negative_cost_abatement_tco2e": round(
            sum(c["annual_abatement_tco2e"] for c in computed if c["is_negative_cost"]), 3),
        "note": ("Levers left of zero on the curve pay for themselves; "
                 "they are the ones to fund first."),
    }


def technology_roadmap(db: Session, *, entity_id: int, horizon_year: int = 2040) -> dict:
    """FR-3.D.3 - sequencing levers by readiness and year."""
    initiatives = list(db.scalars(select(ReductionInitiative).where(
        ReductionInitiative.entity_id == entity_id,
        ReductionInitiative.scenario_id.is_(None))))
    start = min((i.start_year for i in initiatives), default=date.today().year)
    lanes: dict[str, list] = defaultdict(list)
    for i in initiatives:
        lanes[i.technology_readiness or "mature"].append({
            "id": i.id, "name": i.name, "lever_category": i.lever_category,
            "start_year": i.start_year, "end_year": i.end_year,
            "annual_abatement_tco2e": i.annual_abatement_tco2e,
            "capex": i.capex, "status": i.status, "progress_pct": i.progress_pct,
        })
    timeline = []
    for year in range(start, horizon_year + 1):
        active = [i for i in initiatives if i.start_year <= year <= i.end_year]
        timeline.append({
            "year": year,
            "active_initiatives": len(active),
            "cumulative_abatement_tco2e": round(
                sum(i.annual_abatement_tco2e or 0.0 for i in initiatives
                    if i.start_year <= year), 3),
            "capex_in_year": round(
                sum((i.capex or 0.0) / max(1, i.end_year - i.start_year + 1)
                    for i in active), 2),
        })
    return {
        "entity_id": entity_id, "horizon_year": horizon_year,
        "lanes": [{"readiness": k, "initiatives": v} for k, v in lanes.items()],
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# FR-3.D.2  What-if, carbon price, SBTi pathway
# ---------------------------------------------------------------------------

SBTI_ANNUAL_LINEAR_REDUCTION = {"1.5C": 0.042, "WB2C": 0.025, "2C": 0.018}


def sbti_pathway(base_year: int, base_tco2e: float, target_year: int = 2050,
                 ambition: str = "1.5C") -> dict:
    """FR-3.D.2 - SBTi-aligned linear reduction pathway."""
    rate = SBTI_ANNUAL_LINEAR_REDUCTION.get(ambition, 0.042)
    pathway = []
    for year in range(base_year, target_year + 1):
        elapsed = year - base_year
        allowed = max(0.0, base_tco2e * (1 - rate * elapsed))
        pathway.append({"year": year, "allowed_tco2e": round(allowed, 3)})
    return {
        "ambition": ambition, "annual_linear_reduction_pct": round(rate * 100, 2),
        "base_year": base_year, "base_tco2e": round(base_tco2e, 3),
        "target_year": target_year,
        "pathway": pathway,
        "required_reduction_by_2030_pct": round(rate * (2030 - base_year) * 100, 1),
    }


def run_scenario(db: Session, scenario: Scenario) -> dict:
    """FR-3.D.2 / FR-7.8 - evaluate a what-if entirely inside the sandbox.

    Nothing here writes to an actual row: the baseline is *read* from actuals,
    and every projected number lives on the Scenario record.
    """
    assumptions = scenario.assumptions or {}
    entity_id = assumptions.get("entity_id")

    baseline_stmt = select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
        Emission.year == scenario.base_year, Emission.scenario_id.is_(None))
    if entity_id:
        baseline_stmt = baseline_stmt.where(Emission.entity_id == entity_id)
    baseline_kg = float(db.scalar(baseline_stmt) or 0.0)
    baseline_t = baseline_kg / 1000

    growth = float(assumptions.get("annual_growth_pct", 0.0)) / 100.0
    grid_decarb = float(assumptions.get("annual_grid_decarbonization_pct", 0.0)) / 100.0
    supplier_engagement = float(assumptions.get("supplier_engagement_reduction_pct", 0.0)) / 100.0

    levers = list(db.scalars(select(ReductionInitiative).where(
        ReductionInitiative.id.in_(scenario.selected_lever_ids or [0]))))
    price = scenario.internal_carbon_price or 0.0

    trajectory, total_capex = [], 0.0
    for year in range(scenario.base_year, scenario.horizon_year + 1):
        elapsed = year - scenario.base_year
        business_as_usual = baseline_t * ((1 + growth) ** elapsed)
        grid_effect = business_as_usual * (1 - (1 - grid_decarb) ** elapsed) * 0.35
        supplier_effect = business_as_usual * supplier_engagement * min(1.0, elapsed / 5)
        lever_effect = sum(
            (lever.annual_abatement_tco2e or 0.0)
            for lever in levers if lever.start_year <= year
        )
        capex_in_year = sum(
            (lever.capex or 0.0) / max(1, (lever.end_year - lever.start_year + 1))
            for lever in levers if lever.start_year <= year <= lever.end_year
        )
        total_capex += capex_in_year
        projected = max(0.0, business_as_usual - grid_effect - supplier_effect - lever_effect)
        trajectory.append({
            "year": year,
            "business_as_usual_tco2e": round(business_as_usual, 3),
            "projected_tco2e": round(projected, 3),
            "abatement_tco2e": round(business_as_usual - projected, 3),
            "from_levers_tco2e": round(lever_effect, 3),
            "from_grid_tco2e": round(grid_effect, 3),
            "from_suppliers_tco2e": round(supplier_effect, 3),
            "carbon_cost": round(projected * price, 2),
            "capex_in_year": round(capex_in_year, 2),
        })

    final = trajectory[-1] if trajectory else {"projected_tco2e": baseline_t}
    reduction_pct = ((baseline_t - final["projected_tco2e"]) / baseline_t * 100) \
        if baseline_t else 0.0

    target = db.scalars(select(Target).where(Target.entity_id == entity_id)).first() \
        if entity_id else None
    pathway = sbti_pathway(scenario.base_year, baseline_t, scenario.horizon_year,
                           target.sbti_ambition if target else "1.5C")
    allowed_final = pathway["pathway"][-1]["allowed_tco2e"] if pathway["pathway"] else 0.0

    uncertainty_pct = float(assumptions.get("uncertainty_pct", 18.0))
    monte_carlo = unc_engine.monte_carlo(final["projected_tco2e"], uncertainty_pct,
                                         iterations=5000)
    sensitivity = unc_engine.sensitivity(
        final["projected_tco2e"],
        [
            {"name": "Activity growth rate", "contribution": final["projected_tco2e"] * 0.35},
            {"name": "Grid decarbonization", "contribution": final.get("from_grid_tco2e", 0.0)},
            {"name": "Supplier engagement", "contribution": final.get("from_suppliers_tco2e", 0.0)},
            {"name": "Reduction levers", "contribution": final.get("from_levers_tco2e", 0.0)},
        ],
    )

    results = {
        "baseline_year": scenario.base_year,
        "baseline_tco2e": round(baseline_t, 3),
        "horizon_year": scenario.horizon_year,
        "final_projected_tco2e": final["projected_tco2e"],
        "total_reduction_pct": round(reduction_pct, 2),
        "total_capex": round(total_capex, 2),
        "cost_per_tonne_abated": round(
            total_capex / max(0.001, baseline_t - final["projected_tco2e"]), 2),
        "trajectory": trajectory,
        "levers_applied": [
            {"id": l.id, "name": l.name,
             "annual_abatement_tco2e": l.annual_abatement_tco2e, "capex": l.capex}
            for l in levers
        ],
        "internal_carbon_price": price,
        "carbon_cost_at_horizon": final.get("carbon_cost", 0.0),
        "sbti": {
            **pathway,
            "allowed_at_horizon_tco2e": allowed_final,
            "gap_to_pathway_tco2e": round(final["projected_tco2e"] - allowed_final, 3),
            "on_track": final["projected_tco2e"] <= allowed_final,
        },
        "assumptions_used": assumptions,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    scenario.results = results
    scenario.uncertainty = {"monte_carlo": monte_carlo, "sensitivity": sensitivity,
                            "uncertainty_pct": uncertainty_pct}
    scenario.status = "computed"
    db.flush()
    return {"scenario_id": scenario.id, "results": results,
            "uncertainty": scenario.uncertainty}


def carbon_price_impact(db: Session, *, entity_id: int | None, year: int,
                        prices: list[float]) -> dict:
    """FR-3.D.2 - internal carbon price impacts."""
    stmt = select(Emission).where(Emission.year == year, Emission.scenario_id.is_(None))
    if entity_id:
        stmt = stmt.where(Emission.entity_id == entity_id)
    emissions = list(db.scalars(stmt))
    total_t = sum(e.co2e_kg for e in emissions) / 1000
    by_scope: dict[str, float] = defaultdict(float)
    for e in emissions:
        by_scope[e.scope] += e.co2e_kg / 1000

    active = db.scalars(select(InternalCarbonPrice)
                        .where(InternalCarbonPrice.is_active.is_(True))).first()
    return {
        "entity_id": entity_id, "year": year,
        "total_tco2e": round(total_t, 3),
        "active_internal_price": active.price_per_tonne if active else None,
        "scenarios": [
            {
                "price_per_tonne": price,
                "total_carbon_cost": round(total_t * price, 2),
                "by_scope": {k: round(v * price, 2) for k, v in by_scope.items()},
            }
            for price in prices
        ],
    }
