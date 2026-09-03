"""E) Dashboards & Carbon Finance - FR-3.E.1 to FR-3.E.3."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import ScenarioContext, get_scenario_context, scoped
from app.core.serialize import kg_to_t, page_response, rows, to_dict
from app.domain.enums import CreditStatus, Scope, TargetType
from app.domain.models import (
    Baseline, Benchmark, CarbonBudget, Category, ClimateRisk, ClimateScenario,
    CostCenter, CreditOffset, Emission, Entity, Evidence, Facility, Intensity,
    InternalCarbonPrice, Product, ReductionInitiative, Supplier, Target,
)
from app.engine.consolidation import descendant_entity_ids
from app.modules.analytics import service as analytics_service

router = APIRouter(prefix="/dashboards", tags=["E) Dashboards & Carbon Finance"])


def _emissions(db: Session, p: Principal, ctx: ScenarioContext, **filters):
    stmt = select(Emission)
    for key, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(Emission, key) == value)
    return list(db.scalars(ctx.filter(scoped(stmt, Emission, p), Emission)))


# ---------------------------------------------------------------------------
# FR-3.E.1  Executive scorecard
# ---------------------------------------------------------------------------

@router.get("/scorecard/executive")
def executive_scorecard(
    entity_id: int | None = None,
    year: int = Query(default=date.today().year),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    """Total emissions, intensity, targets, trajectories, peer benchmarks,
    exposure, risks and reduction performance - all in one payload."""
    entity_ids = descendant_entity_ids(db, entity_id) if entity_id else None
    stmt = select(Emission).where(Emission.year == year)
    if entity_ids:
        stmt = stmt.where(Emission.entity_id.in_(entity_ids))
    current = list(db.scalars(ctx.filter(scoped(stmt, Emission, p), Emission)))

    prior_stmt = select(Emission).where(Emission.year == year - 1)
    if entity_ids:
        prior_stmt = prior_stmt.where(Emission.entity_id.in_(entity_ids))
    prior = list(db.scalars(ctx.filter(scoped(prior_stmt, Emission, p), Emission)))

    total_kg = sum(e.co2e_kg for e in current)
    prior_kg = sum(e.co2e_kg for e in prior)
    by_scope: dict[str, float] = defaultdict(float)
    for e in current:
        by_scope[e.scope] += e.co2e_kg

    entity = db.get(Entity, entity_id) if entity_id else None
    entities = [db.get(Entity, i) for i in (entity_ids or [])] if entity_ids else \
        list(db.scalars(scoped(select(Entity), Entity, p)))
    entities = [e for e in entities if e]
    revenue = sum(e.revenue or 0.0 for e in entities)
    employees = sum(e.employees or 0 for e in entities)

    # Targets and trajectory
    target_stmt = select(Target)
    if entity_ids:
        target_stmt = target_stmt.where(Target.entity_id.in_(entity_ids))
    targets = list(db.scalars(scoped(target_stmt, Target, p)))
    target_rows = []
    for t in targets:
        allowed = t.base_value * (1 - t.reduction_pct / 100 *
                                  (year - t.base_year) / max(1, t.target_year - t.base_year))
        target_rows.append({
            **to_dict(t),
            "allowed_this_year_tco2e": round(allowed, 3),
            "actual_tco2e": round(total_kg / 1000, 3),
            "variance_tco2e": round(total_kg / 1000 - allowed, 3),
            "on_track": (total_kg / 1000) <= allowed,
            "progress_pct": round(
                (t.base_value - total_kg / 1000) / (t.base_value * t.reduction_pct / 100) * 100, 1
            ) if t.base_value and t.reduction_pct else 0.0,
        })

    # Peer benchmarks
    industry = entity.organization.industry if entity and entity.organization else None
    benchmarks = list(db.scalars(select(Benchmark).where(Benchmark.year == year)))
    if industry:
        benchmarks = [b for b in benchmarks if b.industry == industry] or benchmarks

    intensity_revenue = (total_kg / 1000) / revenue * 1_000_000 if revenue else 0.0
    intensity_employee = (total_kg / 1000) / employees if employees else 0.0

    # Financial exposure at the active internal carbon price
    price_row = db.scalars(select(InternalCarbonPrice)
                           .where(InternalCarbonPrice.is_active.is_(True))).first()
    price = price_row.price_per_tonne if price_row else 0.0

    risk_stmt = select(ClimateRisk)
    if entity_ids:
        risk_stmt = risk_stmt.where(ClimateRisk.entity_id.in_(entity_ids))
    risks = list(db.scalars(scoped(risk_stmt, ClimateRisk, p)))

    initiatives_stmt = select(ReductionInitiative).where(
        ReductionInitiative.scenario_id.is_(None))
    if entity_ids:
        initiatives_stmt = initiatives_stmt.where(
            ReductionInitiative.entity_id.in_(entity_ids))
    initiatives = list(db.scalars(scoped(initiatives_stmt, ReductionInitiative, p)))

    trajectory_rows = db.execute(
        select(Emission.year, func.sum(Emission.co2e_kg))
        .where(Emission.scenario_id.is_(None)
               if ctx.scenario_id is None else Emission.scenario_id == ctx.scenario_id)
        .group_by(Emission.year).order_by(Emission.year)
    ).all()

    return {
        "entity_id": entity_id,
        "entity_name": entity.name if entity else "All permitted entities",
        "year": year,
        "scenario_id": ctx.scenario_id,
        "is_sandbox": ctx.is_sandbox,
        "total_emissions": {
            "tco2e": round(total_kg / 1000, 3),
            "prior_year_tco2e": round(prior_kg / 1000, 3),
            "yoy_delta_tco2e": round((total_kg - prior_kg) / 1000, 3),
            "yoy_delta_pct": round((total_kg - prior_kg) / prior_kg * 100, 2)
            if prior_kg else 0.0,
            "by_scope": [
                {"scope": s.value, "tco2e": round(by_scope.get(s.value, 0.0) / 1000, 3),
                 "share_pct": round(by_scope.get(s.value, 0.0) / total_kg * 100, 2)
                 if total_kg else 0.0}
                for s in Scope
            ],
        },
        "intensity": {
            "per_million_revenue": round(intensity_revenue, 3),
            "per_employee": round(intensity_employee, 3),
            "revenue": revenue, "employees": employees,
            "currency": entity.organization.reporting_currency
            if entity and entity.organization else "EUR",
        },
        "targets": target_rows,
        "trajectory": [
            {"year": int(r[0]), "tco2e": round(float(r[1]) / 1000, 3)}
            for r in trajectory_rows
        ],
        "peer_benchmarks": [
            {**to_dict(b),
             "our_value": round(intensity_revenue, 3) if "revenue" in b.metric
             else round(total_kg / 1000, 3),
             "vs_median_pct": round(
                 (intensity_revenue - b.peer_median) / b.peer_median * 100, 2)
             if b.peer_median and "revenue" in b.metric else None}
            for b in benchmarks
        ],
        "exposure": {
            "internal_carbon_price": price,
            "carbon_liability": round(total_kg / 1000 * price, 2),
            "share_of_revenue_pct": round(
                (total_kg / 1000 * price) / revenue * 100, 3) if revenue else 0.0,
        },
        "risks": {
            "count": len(risks),
            "opportunities": sum(1 for r in risks if r.is_opportunity),
            "high_impact": sum(1 for r in risks if r.impact_rating in ("high", "severe")),
            "financial_impact_range": {
                "low": round(sum(r.financial_impact_low for r in risks
                                 if not r.is_opportunity), 2),
                "high": round(sum(r.financial_impact_high for r in risks
                                  if not r.is_opportunity), 2),
            },
            "top_risks": [
                {"title": r.title, "risk_type": r.risk_type, "horizon": r.horizon,
                 "impact_rating": r.impact_rating,
                 "financial_impact_high": r.financial_impact_high}
                for r in sorted(risks, key=lambda x: -x.financial_impact_high)[:5]
            ],
        },
        "reduction_performance": {
            "initiative_count": len(initiatives),
            "planned_annual_abatement_tco2e": round(
                sum(i.annual_abatement_tco2e or 0 for i in initiatives), 3),
            "realized_annual_abatement_tco2e": round(
                sum(i.realized_abatement_tco2e or 0 for i in initiatives), 3),
            "total_capex": round(sum(i.capex or 0 for i in initiatives), 2),
            "in_delivery": sum(1 for i in initiatives if i.status == "in_delivery"),
            "completed": sum(1 for i in initiatives if i.status == "completed"),
        },
        "data_quality": {
            "record_count": len(current),
            "average_confidence": round(
                sum(e.confidence_score for e in current) / len(current), 2)
            if current else 0.0,
            "estimated_share_pct": round(
                sum(e.co2e_kg for e in current if e.is_estimated) / total_kg * 100, 2)
            if total_kg else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# FR-3.E.2  Operational drill-down
# ---------------------------------------------------------------------------

DRILL_DIMENSIONS = ["entity", "facility", "cost_center", "product", "supplier",
                    "project", "category", "geography", "period", "data_quality"]


@router.get("/drilldown")
def drilldown(
    dimension: str = Query(default="entity"),
    year: int | None = None, scope: str | None = None,
    entity_id: int | None = None, facility_id: int | None = None,
    supplier_id: int | None = None, product_id: int | None = None,
    category_id: int | None = None, country: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    """Drill down by every dimension FR-3.E.2 lists."""
    if dimension not in DRILL_DIMENSIONS:
        raise HTTPException(400, f"dimension must be one of {DRILL_DIMENSIONS}")

    stmt = select(Emission)
    for col, val in (("year", year), ("scope", scope), ("entity_id", entity_id),
                     ("facility_id", facility_id), ("supplier_id", supplier_id),
                     ("product_id", product_id), ("category_id", category_id),
                     ("country", country)):
        if val is not None:
            stmt = stmt.where(getattr(Emission, col) == val)
    emissions = list(db.scalars(ctx.filter(scoped(stmt, Emission, p), Emission)))

    buckets: dict[str, dict] = {}

    def bucket(key: str, extra: dict | None = None) -> dict:
        b = buckets.setdefault(key, {
            "key": key, "co2e_kg": 0.0, "record_count": 0,
            "estimated_kg": 0.0, "confidence_sum": 0.0, **(extra or {})})
        return b

    for e in emissions:
        if dimension == "entity":
            obj = db.get(Entity, e.entity_id)
            b = bucket(obj.name if obj else str(e.entity_id),
                       {"id": e.entity_id, "country": obj.country if obj else ""})
        elif dimension == "facility":
            obj = db.get(Facility, e.facility_id) if e.facility_id else None
            b = bucket(obj.name if obj else "Unassigned",
                       {"id": e.facility_id, "country": obj.country if obj else "",
                        "facility_type": obj.facility_type if obj else ""})
        elif dimension == "cost_center":
            obj = db.get(CostCenter, e.cost_center_id) if e.cost_center_id else None
            b = bucket(obj.name if obj else "Unassigned", {"id": e.cost_center_id,
                                                           "code": obj.code if obj else ""})
        elif dimension == "product":
            obj = db.get(Product, e.product_id) if e.product_id else None
            b = bucket(f"{obj.sku} - {obj.name}" if obj else "No product",
                       {"id": e.product_id})
        elif dimension == "supplier":
            obj = db.get(Supplier, e.supplier_id) if e.supplier_id else None
            b = bucket(obj.name if obj else "No supplier",
                       {"id": e.supplier_id, "tier": obj.tier if obj else None,
                        "country": obj.country if obj else ""})
        elif dimension == "project":
            b = bucket("Attributed to reduction initiatives"
                       if e.scenario_id else "Business as usual")
        elif dimension == "category":
            obj = db.get(Category, e.category_id) if e.category_id else None
            b = bucket(obj.name if obj else f"{e.scope} (uncategorized)",
                       {"id": e.category_id, "number": obj.number if obj else None,
                        "scope": e.scope})
        elif dimension == "geography":
            b = bucket(e.country or "Unknown", {"country": e.country})
        elif dimension == "period":
            b = bucket(str(e.year), {"year": e.year})
        else:  # data_quality
            b = bucket(e.data_quality_rating or "unrated",
                       {"rating": e.data_quality_rating})
        b["co2e_kg"] += e.co2e_kg
        b["record_count"] += 1
        b["confidence_sum"] += e.confidence_score
        if e.is_estimated:
            b["estimated_kg"] += e.co2e_kg

    total = sum(b["co2e_kg"] for b in buckets.values())
    items = []
    for b in buckets.values():
        items.append({
            **{k: v for k, v in b.items()
               if k not in ("co2e_kg", "confidence_sum", "estimated_kg")},
            "tco2e": round(b["co2e_kg"] / 1000, 3),
            "share_pct": round(b["co2e_kg"] / total * 100, 2) if total else 0.0,
            "average_confidence": round(b["confidence_sum"] / b["record_count"], 1)
            if b["record_count"] else 0.0,
            "estimated_share_pct": round(b["estimated_kg"] / b["co2e_kg"] * 100, 2)
            if b["co2e_kg"] else 0.0,
        })
    items.sort(key=lambda i: i["tco2e"], reverse=True)
    return {
        "dimension": dimension,
        "available_dimensions": DRILL_DIMENSIONS,
        "filters": {"year": year, "scope": scope, "entity_id": entity_id,
                    "facility_id": facility_id, "supplier_id": supplier_id,
                    "product_id": product_id, "category_id": category_id,
                    "country": country},
        "total_tco2e": round(total / 1000, 3),
        "record_count": len(emissions),
        "items": items,
        "scenario_id": ctx.scenario_id,
    }


@router.get("/trend")
def trend(entity_id: int | None = None, scope: str | None = None,
          group_by: str = Query(default="year", pattern="^(year|scope|country)$"),
          db: Session = Depends(get_db), p: Principal = Depends(get_principal),
          ctx: ScenarioContext = Depends(get_scenario_context)):
    stmt = select(Emission)
    if entity_id:
        stmt = stmt.where(Emission.entity_id.in_(descendant_entity_ids(db, entity_id)))
    if scope:
        stmt = stmt.where(Emission.scope == scope)
    emissions = list(db.scalars(ctx.filter(scoped(stmt, Emission, p), Emission)))
    series: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in emissions:
        key = e.scope if group_by == "scope" else (e.country if group_by == "country" else "total")
        series[e.year][key] += e.co2e_kg / 1000
    return {
        "group_by": group_by,
        "series": [
            {"year": year, **{k: round(v, 3) for k, v in values.items()}}
            for year, values in sorted(series.items())
        ],
    }


# ---------------------------------------------------------------------------
# FR-3.E.3  Carbon finance
# ---------------------------------------------------------------------------

@router.get("/carbon-budgets")
def list_budgets(entity_id: int | None = None, year: int | None = None,
                 db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(CarbonBudget).order_by(CarbonBudget.year.desc())
    if entity_id:
        stmt = stmt.where(CarbonBudget.entity_id == entity_id)
    if year:
        stmt = stmt.where(CarbonBudget.year == year)
    budgets = list(db.scalars(scoped(stmt, CarbonBudget, p)))
    out = []
    for b in budgets:
        consumed_kg = db.scalar(
            select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
                Emission.entity_id == b.entity_id, Emission.year == b.year,
                Emission.scenario_id.is_(None))
        ) or 0.0
        b.consumed_tco2e = round(float(consumed_kg) / 1000, 3)
        usage = b.consumed_tco2e / b.budget_tco2e * 100 if b.budget_tco2e else 0.0
        b.status = "exceeded" if usage > 100 else "at_risk" if usage > 90 else "on_track"
        entity = db.get(Entity, b.entity_id)
        out.append({**to_dict(b),
                    "entity_name": entity.name if entity else None,
                    "usage_pct": round(usage, 2),
                    "remaining_tco2e": round(b.budget_tco2e - b.consumed_tco2e, 3)})
    db.commit()
    return out


class BudgetIn(BaseModel):
    entity_id: int
    year: int
    scope: str = "all"
    budget_tco2e: float
    owner: str = ""


@router.post("/carbon-budgets", status_code=201)
def create_budget(payload: BudgetIn, db: Session = Depends(get_db),
                  p: Principal = Depends(require("finance.write"))):
    b = CarbonBudget(**payload.model_dump())
    db.add(b)
    db.commit()
    return to_dict(b)


@router.get("/internal-pricing")
def list_internal_prices(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    return rows(db.scalars(select(InternalCarbonPrice)
                           .order_by(InternalCarbonPrice.effective_from.desc())))


class PriceIn(BaseModel):
    organization_id: int
    name: str
    price_type: str = "shadow"
    price_per_tonne: float
    currency: str = "EUR"
    effective_from: date
    scopes_covered: list[str] = Field(default_factory=lambda: [s.value for s in Scope])
    applies_to: str = "capex_decisions"


@router.post("/internal-pricing", status_code=201)
def create_internal_price(payload: PriceIn, db: Session = Depends(get_db),
                          p: Principal = Depends(require("finance.write"))):
    price = InternalCarbonPrice(**payload.model_dump())
    db.add(price)
    db.commit()
    return to_dict(price)


@router.get("/credits")
def list_credits(organization_id: int | None = None, status: str | None = None,
                 page: int = 1, page_size: int = 50,
                 db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.E.3 - credit/offset registry."""
    stmt = select(CreditOffset).order_by(CreditOffset.vintage_year.desc())
    if organization_id:
        stmt = stmt.where(CreditOffset.organization_id == organization_id)
    if status:
        stmt = stmt.where(CreditOffset.status == status)

    def mapper(c: CreditOffset) -> dict:
        evidence = db.get(Evidence, c.retirement_evidence_id) \
            if c.retirement_evidence_id else None
        return to_dict(c, extra={
            "total_value": round(c.quantity_tco2e * c.price_per_tonne, 2),
            "retirement_evidence": to_dict(evidence) if evidence else None,
            "has_retirement_evidence": evidence is not None,
        })

    return page_response(db, scoped(stmt, CreditOffset, p), page=page,
                         page_size=page_size, mapper=mapper)


@router.get("/credits/summary")
def credit_summary(organization_id: int, year: int = Query(default=date.today().year),
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    credits = list(db.scalars(select(CreditOffset)
                              .where(CreditOffset.organization_id == organization_id)))
    held = [c for c in credits if c.status == CreditStatus.HELD]
    retired = [c for c in credits if c.status == CreditStatus.RETIRED]
    gross_kg = db.scalar(
        select(func.coalesce(func.sum(Emission.co2e_kg), 0.0))
        .where(Emission.year == year, Emission.scenario_id.is_(None))) or 0.0
    gross_t = float(gross_kg) / 1000
    retired_t = sum(c.quantity_tco2e for c in retired)
    return {
        "organization_id": organization_id, "year": year,
        "held_tco2e": round(sum(c.quantity_tco2e for c in held), 3),
        "retired_tco2e": round(retired_t, 3),
        "held_value": round(sum(c.quantity_tco2e * c.price_per_tonne for c in held), 2),
        "retired_value": round(sum(c.quantity_tco2e * c.price_per_tonne for c in retired), 2),
        "removals_share_pct": round(
            sum(c.quantity_tco2e for c in retired if c.is_removal) / retired_t * 100, 2)
        if retired_t else 0.0,
        "gross_emissions_tco2e": round(gross_t, 3),
        "net_after_retirement_tco2e": round(gross_t - retired_t, 3),
        "offset_coverage_pct": round(retired_t / gross_t * 100, 2) if gross_t else 0.0,
        "retirement_evidence_complete": all(
            c.retirement_evidence_id for c in retired) if retired else True,
        "by_registry": [
            {"registry": r,
             "tco2e": round(sum(c.quantity_tco2e for c in credits if c.registry == r), 3)}
            for r in sorted({c.registry for c in credits})
        ],
        "note": ("Gross emissions are reported before any retirement. Offsets are "
                 "disclosed separately and never netted into the gross figure."),
    }


@router.post("/credits/{credit_id}/retire")
def retire_credit(
    credit_id: int, reason: str = Body(...), evidence_title: str = Body(default=""),
    evidence_reference: str = Body(default=""),
    db: Session = Depends(get_db), p: Principal = Depends(require("finance.write")),
):
    """FR-3.E.3 - retirement always carries evidence."""
    credit = db.get(CreditOffset, credit_id)
    if credit is None:
        raise HTTPException(404, "Credit not found")
    if credit.status == CreditStatus.RETIRED:
        raise HTTPException(409, "Credit is already retired")
    evidence = Evidence(
        organization_id=credit.organization_id,
        object_type="credit_offset", object_id=credit.id,
        title=evidence_title or f"Retirement certificate {credit.serial_number}",
        evidence_type="retirement_certificate", status="accepted",
        extracted_fields={"registry": credit.registry,
                          "serial_number": credit.serial_number,
                          "reference": evidence_reference,
                          "quantity_tco2e": credit.quantity_tco2e},
        uploaded_by_id=p.user.id,
    )
    db.add(evidence)
    db.flush()
    credit.status = CreditStatus.RETIRED
    credit.retired_at = datetime.now(timezone.utc)
    credit.retirement_reason = reason
    credit.retirement_evidence_id = evidence.id
    db.commit()
    return {**to_dict(credit), "retirement_evidence": to_dict(evidence)}


@router.get("/project-economics")
def project_economics(entity_id: int | None = None, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    """FR-3.E.3 - project economics and investment prioritization."""
    macc = analytics_service.build_macc(db, entity_id=entity_id)
    db.commit()
    price_row = db.scalars(select(InternalCarbonPrice)
                           .where(InternalCarbonPrice.is_active.is_(True))).first()
    price = price_row.price_per_tonne if price_row else 0.0
    projects = []
    for c in macc["curve"]:
        lifetime_abatement = c["lifetime_abatement_tco2e"]
        carbon_value = lifetime_abatement * price
        net_cost = (c["capex"] or 0) + (c["annual_opex_delta"] or 0) * c["lifetime_years"]
        npv = carbon_value - net_cost
        projects.append({
            **c,
            "carbon_value_at_internal_price": round(carbon_value, 2),
            "net_lifetime_cost": round(net_cost, 2),
            "npv_at_internal_price": round(npv, 2),
            "funds_itself": npv >= 0,
        })
    projects.sort(key=lambda x: (-x["npv_at_internal_price"],
                                x["marginal_abatement_cost"]))
    for rank, project in enumerate(projects, 1):
        project["investment_rank"] = rank
    return {
        "entity_id": entity_id,
        "internal_carbon_price": price,
        "total_capex_required": macc["total_capex"],
        "total_annual_abatement_tco2e": macc["total_annual_abatement_tco2e"],
        "self_funding_projects": sum(1 for p_ in projects if p_["funds_itself"]),
        "projects": projects,
    }


@router.get("/tcfd/financial-impacts")
def tcfd_financial_impacts(entity_id: int | None = None,
                           db: Session = Depends(get_db),
                           p: Principal = Depends(get_principal)):
    """FR-3.E.3 / FR-4.3 - TCFD financial impacts rolled up for the dashboard."""
    stmt = select(ClimateRisk)
    if entity_id:
        stmt = stmt.where(ClimateRisk.entity_id.in_(descendant_entity_ids(db, entity_id)))
    risks = list(db.scalars(scoped(stmt, ClimateRisk, p)))
    scenario_stmt = select(ClimateScenario)
    if entity_id:
        scenario_stmt = scenario_stmt.where(ClimateScenario.entity_id == entity_id)
    scenarios = list(db.scalars(scoped(scenario_stmt, ClimateScenario, p)))

    by_horizon: dict[str, dict] = {}
    by_type: dict[str, dict] = {}
    for r in risks:
        h = by_horizon.setdefault(r.horizon, {"horizon": r.horizon, "low": 0.0,
                                              "high": 0.0, "count": 0})
        h["low"] += r.financial_impact_low * (-1 if r.is_opportunity else 1)
        h["high"] += r.financial_impact_high * (-1 if r.is_opportunity else 1)
        h["count"] += 1
        t = by_type.setdefault(r.risk_type, {"risk_type": r.risk_type, "low": 0.0,
                                             "high": 0.0, "count": 0})
        t["low"] += r.financial_impact_low
        t["high"] += r.financial_impact_high
        t["count"] += 1

    return {
        "entity_id": entity_id,
        "risk_count": len(risks),
        "opportunity_count": sum(1 for r in risks if r.is_opportunity),
        "net_exposure": {
            "low": round(sum(h["low"] for h in by_horizon.values()), 2),
            "high": round(sum(h["high"] for h in by_horizon.values()), 2),
        },
        "by_horizon": [{**h, "low": round(h["low"], 2), "high": round(h["high"], 2)}
                       for h in by_horizon.values()],
        "by_risk_type": [{**t, "low": round(t["low"], 2), "high": round(t["high"], 2)}
                         for t in sorted(by_type.values(), key=lambda x: -x["high"])],
        "scenarios": [
            {**to_dict(s)} for s in scenarios
        ],
        "risks": rows(risks),
    }


@router.get("/intensity")
def intensity_metrics(entity_id: int | None = None, year: int = Query(default=date.today().year),
                      db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Intensity).where(Intensity.year == year)
    if entity_id:
        stmt = stmt.where(Intensity.entity_id == entity_id)
    stored = rows(db.scalars(scoped(stmt, Intensity, p)))

    entities = list(db.scalars(scoped(select(Entity), Entity, p)))
    computed = []
    for e in entities:
        if entity_id and e.id != entity_id:
            continue
        kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.entity_id == e.id, Emission.year == year,
            Emission.scenario_id.is_(None))) or 0.0
        tonnes = float(kg) / 1000
        computed.append({
            "entity_id": e.id, "entity_name": e.name, "year": year,
            "tco2e": round(tonnes, 3),
            "per_million_revenue": round(tonnes / e.revenue * 1_000_000, 4)
            if e.revenue else None,
            "per_employee": round(tonnes / e.employees, 4) if e.employees else None,
            "revenue": e.revenue, "employees": e.employees,
        })
    return {"year": year, "stored": stored, "computed": computed}


@router.get("/targets")
def list_targets(entity_id: int | None = None, db: Session = Depends(get_db),
                 p: Principal = Depends(get_principal)):
    stmt = select(Target)
    if entity_id:
        stmt = stmt.where(Target.entity_id == entity_id)
    targets = list(db.scalars(scoped(stmt, Target, p)))
    out = []
    for t in targets:
        actuals = db.execute(
            select(Emission.year, func.sum(Emission.co2e_kg))
            .where(Emission.entity_id == t.entity_id, Emission.scenario_id.is_(None))
            .group_by(Emission.year).order_by(Emission.year)).all()
        actual_map = {int(r[0]): float(r[1]) / 1000 for r in actuals}
        trajectory = []
        span = max(1, t.target_year - t.base_year)
        for year in range(t.base_year, t.target_year + 1):
            allowed = t.base_value * (1 - t.reduction_pct / 100 * (year - t.base_year) / span)
            trajectory.append({
                "year": year, "allowed_tco2e": round(allowed, 3),
                "actual_tco2e": round(actual_map[year], 3) if year in actual_map else None,
                "on_track": actual_map[year] <= allowed if year in actual_map else None,
            })
        out.append({**to_dict(t), "computed_trajectory": trajectory,
                    "target_types": [x.value for x in TargetType]})
    return out


@router.get("/geography")
def geography(year: int = Query(default=date.today().year),
              db: Session = Depends(get_db), p: Principal = Depends(get_principal),
              ctx: ScenarioContext = Depends(get_scenario_context)):
    """Country roll-up with facility pins - drives the map view (FR-3.E.2)."""
    emissions = _emissions(db, p, ctx, year=year)
    by_country: dict[str, dict] = {}
    for e in emissions:
        c = by_country.setdefault(e.country or "??", {
            "country": e.country or "??", "co2e_kg": 0.0, "record_count": 0})
        c["co2e_kg"] += e.co2e_kg
        c["record_count"] += 1
    facilities = list(db.scalars(scoped(select(Facility), Facility, p)))
    pins = []
    for f in facilities:
        kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.facility_id == f.id, Emission.year == year,
            Emission.scenario_id.is_(None))) or 0.0
        pins.append({"facility_id": f.id, "name": f.name, "country": f.country,
                     "latitude": f.latitude, "longitude": f.longitude,
                     "facility_type": f.facility_type,
                     "tco2e": round(float(kg) / 1000, 3)})
    total = sum(c["co2e_kg"] for c in by_country.values())
    return {
        "year": year,
        "countries": sorted(
            [{"country": c["country"], "tco2e": round(c["co2e_kg"] / 1000, 3),
              "record_count": c["record_count"],
              "share_pct": round(c["co2e_kg"] / total * 100, 2) if total else 0.0}
             for c in by_country.values()],
            key=lambda c: -c["tco2e"]),
        "facilities": sorted(pins, key=lambda f: -f["tco2e"]),
    }
