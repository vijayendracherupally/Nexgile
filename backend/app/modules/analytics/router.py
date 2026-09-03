"""D) AI Analytics & Reduction Planning - FR-3.D.1 to FR-3.D.4."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import (
    ScenarioContext, ScenarioIsolationError, get_scenario_context, guard_scenario_write, scoped,
)
from app.core.serialize import page_response, rows, to_dict
from app.domain.models import (
    ActivityData, Anomaly, Approval, AuditLog, Calculation, DataGap,
    DataQualityAssessment, Emission, EmissionFactor, Entity, ReductionInitiative,
    Scenario, Transaction,
)
from app.engine import uncertainty as unc_engine
from app.modules.analytics import service
from app.modules.suppliers.service import extract_from_document

router = APIRouter(prefix="/analytics", tags=["D) AI Analytics & Reduction Planning"])


# ---------------------------------------------------------------------------
# FR-3.D.1  Spend categorization, extraction, anomalies, gaps, forecasting
# ---------------------------------------------------------------------------

@router.post("/spend/categorize")
def categorize_spend(entity_id: int | None = Body(default=None, embed=True),
                     db: Session = Depends(get_db),
                     p: Principal = Depends(require("analytics.write"))):
    """FR-3.D.1 - automated spend categorization into Scope 3 categories."""
    result = service.run_spend_categorization(db, entity_id=entity_id)
    db.commit()
    return result


@router.get("/spend/preview")
def preview_categorization(description: str, gl_account: str = ""):
    number, confidence, method = service.categorize_spend(description, gl_account)
    return {"description": description, "category_number": number,
            "confidence": confidence, "method": method,
            "requires_review": confidence < 0.7}


@router.get("/spend/uncategorized")
def uncategorized_spend(entity_id: int | None = None, page: int = 1, page_size: int = 50,
                        db: Session = Depends(get_db),
                        p: Principal = Depends(get_principal)):
    stmt = select(Transaction).where(Transaction.category_id.is_(None)) \
        .order_by(Transaction.amount.desc())
    if entity_id:
        stmt = stmt.where(Transaction.entity_id == entity_id)
    return page_response(db, scoped(stmt, Transaction, p), page=page, page_size=page_size)


@router.post("/documents/extract")
def extract_document(text: str = Body(..., embed=True)):
    """FR-3.D.1 - invoice/document extraction."""
    return extract_from_document(text)


@router.post("/anomalies/detect")
def detect_anomalies(entity_id: int | None = Body(default=None),
                     z_threshold: float = Body(default=2.0),
                     db: Session = Depends(get_db),
                     p: Principal = Depends(require("analytics.write"))):
    """FR-3.D.1 - emissions anomaly detection."""
    found = service.detect_anomalies(db, entity_id=entity_id, z_threshold=z_threshold)
    db.commit()
    return {"detected": len(found), "z_threshold": z_threshold, "anomalies": found[:200]}


@router.get("/anomalies")
def list_anomalies(status: str | None = None, severity: str | None = None,
                   entity_id: int | None = None, page: int = 1, page_size: int = 50,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Anomaly).order_by(Anomaly.detected_at.desc())
    if status:
        stmt = stmt.where(Anomaly.status == status)
    if severity:
        stmt = stmt.where(Anomaly.severity == severity)
    if entity_id:
        stmt = stmt.where(Anomaly.entity_id == entity_id)
    return page_response(db, scoped(stmt, Anomaly, p), page=page, page_size=page_size)


@router.patch("/anomalies/{anomaly_id}")
def update_anomaly(anomaly_id: int, status: str = Body(..., embed=True),
                   db: Session = Depends(get_db),
                   p: Principal = Depends(require("analytics.write"))):
    a = db.get(Anomaly, anomaly_id)
    if a is None:
        raise HTTPException(404, "Anomaly not found")
    a.status = status
    db.commit()
    return to_dict(a)


@router.post("/gaps/identify")
def identify_gaps(entity_id: int = Body(...), year: int = Body(default=date.today().year),
                  db: Session = Depends(get_db),
                  p: Principal = Depends(require("analytics.write"))):
    """FR-3.D.1 / FR-7.4 - gap identification with estimation basis."""
    gaps = service.identify_gaps(db, entity_id=entity_id, year=year)
    db.commit()
    return {"entity_id": entity_id, "year": year, "gap_count": len(gaps), "gaps": gaps}


@router.get("/gaps")
def list_gaps(entity_id: int | None = None, year: int | None = None,
              status: str | None = None,
              db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(DataGap).order_by(DataGap.estimated_co2e_kg.desc())
    if entity_id:
        stmt = stmt.where(DataGap.entity_id == entity_id)
    if year:
        stmt = stmt.where(DataGap.period_year == year)
    if status:
        stmt = stmt.where(DataGap.status == status)
    return rows(db.scalars(scoped(stmt, DataGap, p)))


@router.get("/forecast")
def forecast(entity_id: int, horizon_years: int = 5, scope: str | None = None,
             db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.D.1 - predictive forecasting."""
    return service.forecast(db, entity_id=entity_id, horizon_years=horizon_years, scope=scope)


# ---------------------------------------------------------------------------
# FR-3.D.2  Scenarios: what-if, Monte Carlo, sensitivity, carbon price, SBTi
# ---------------------------------------------------------------------------

class ScenarioIn(BaseModel):
    organization_id: int
    name: str
    scenario_type: str = "what_if"
    base_year: int = date.today().year
    horizon_year: int = 2030
    description: str = ""
    assumptions: dict = Field(default_factory=dict)
    selected_lever_ids: list[int] = Field(default_factory=list)
    internal_carbon_price: float = 0.0


@router.post("/scenarios", status_code=201)
def create_scenario(payload: ScenarioIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("scenario.write"))):
    """FR-7.8 - a scenario is a separate address space, never a copy of actuals."""
    s = Scenario(**payload.model_dump(), created_by_id=p.user.id)
    db.add(s)
    db.commit()
    return to_dict(s)


@router.get("/scenarios")
def list_scenarios(organization_id: int | None = None, db: Session = Depends(get_db),
                   p: Principal = Depends(get_principal)):
    stmt = select(Scenario).order_by(Scenario.id.desc())
    if organization_id:
        stmt = stmt.where(Scenario.organization_id == organization_id)
    return [to_dict(s, exclude={"results", "uncertainty"}) for s in db.scalars(stmt)]


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    return to_dict(s)


@router.patch("/scenarios/{scenario_id}")
def update_scenario(scenario_id: int, payload: dict = Body(...),
                    db: Session = Depends(get_db),
                    p: Principal = Depends(require("scenario.write"))):
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    if s.is_locked:
        raise HTTPException(409, "Scenario is locked")
    for k, v in payload.items():
        if hasattr(s, k) and k not in ("id", "organization_id"):
            setattr(s, k, v)
    db.commit()
    return to_dict(s)


@router.post("/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: int, db: Session = Depends(get_db),
                 p: Principal = Depends(require("scenario.write"))):
    """FR-3.D.2 - what-if modelling. Reads actuals, writes only the sandbox."""
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    result = service.run_scenario(db, s)
    db.commit()
    return {
        **result,
        "isolation_note": (
            "FR-7.8: this run read approved actuals as its baseline and wrote nothing "
            "back to them. All projected values live on the scenario."
        ),
    }


@router.post("/scenarios/{scenario_id}/monte-carlo")
def scenario_monte_carlo(
    scenario_id: int, uncertainty_pct: float = Body(default=18.0),
    iterations: int = Body(default=10000), distribution: str = Body(default="lognormal"),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    """FR-3.D.2 - Monte Carlo uncertainty."""
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    mean = (s.results or {}).get("final_projected_tco2e", 0.0)
    if not mean:
        raise HTTPException(409, "Run the scenario before sampling its uncertainty")
    return unc_engine.monte_carlo(mean, uncertainty_pct, iterations, distribution)


@router.post("/scenarios/{scenario_id}/sensitivity")
def scenario_sensitivity(scenario_id: int, delta_pct: float = Body(default=10.0, embed=True),
                         db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.D.2 - sensitivity analysis (tornado)."""
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    results = s.results or {}
    base = results.get("final_projected_tco2e", 0.0)
    trajectory = results.get("trajectory") or []
    final = trajectory[-1] if trajectory else {}
    drivers = [
        {"name": "Activity growth rate", "contribution": base * 0.35},
        {"name": "Grid decarbonization", "contribution": final.get("from_grid_tco2e", 0.0)},
        {"name": "Supplier engagement", "contribution": final.get("from_suppliers_tco2e", 0.0)},
        {"name": "Reduction levers", "contribution": final.get("from_levers_tco2e", 0.0)},
        {"name": "Emission factor uncertainty", "contribution": base * 0.12},
    ]
    return {"base_tco2e": base, "delta_pct": delta_pct,
            "drivers": unc_engine.sensitivity(base, drivers, delta_pct)}


@router.post("/scenarios/compare")
def compare_scenarios(scenario_ids: list[int] = Body(..., embed=True),
                      db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-7.8 - comparisons show assumptions, versions, uncertainty and levers."""
    out = []
    for sid in scenario_ids:
        s = db.get(Scenario, sid)
        if s is None:
            continue
        results = s.results or {}
        out.append({
            "scenario_id": s.id, "name": s.name, "type": s.scenario_type,
            "status": s.status,
            "base_year": s.base_year, "horizon_year": s.horizon_year,
            "baseline_tco2e": results.get("baseline_tco2e"),
            "final_projected_tco2e": results.get("final_projected_tco2e"),
            "total_reduction_pct": results.get("total_reduction_pct"),
            "total_capex": results.get("total_capex"),
            "cost_per_tonne_abated": results.get("cost_per_tonne_abated"),
            "assumptions": s.assumptions,
            "selected_lever_ids": s.selected_lever_ids,
            "levers_applied": results.get("levers_applied", []),
            "internal_carbon_price": s.internal_carbon_price,
            "method_version": s.method_version,
            "factor_library_version": s.factor_library_version,
            "uncertainty": s.uncertainty,
            "sbti_on_track": (results.get("sbti") or {}).get("on_track"),
            "trajectory": results.get("trajectory", []),
        })
    return {
        "scenarios": out,
        "comparison_note": (
            "Every scenario is isolated from approved actuals (FR-7.8). Differences "
            "below stem from the assumptions, factor/method versions and selected "
            "levers shown on each row."
        ),
    }


@router.post("/carbon-price/impact")
def carbon_price_impact(
    entity_id: int | None = Body(default=None),
    year: int = Body(default=date.today().year),
    prices: list[float] = Body(default=[0, 50, 100, 150, 200]),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    """FR-3.D.2 - internal carbon price impacts."""
    return service.carbon_price_impact(db, entity_id=entity_id, year=year, prices=prices)


@router.get("/pathways/sbti")
def sbti(entity_id: int, base_year: int | None = None, target_year: int = 2050,
         ambition: str = "1.5C", db: Session = Depends(get_db),
         p: Principal = Depends(get_principal)):
    """FR-3.D.2 - SBTi-aligned pathway optimization."""
    base_year = base_year or (date.today().year - 1)
    base_kg = db.scalar(
        select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.entity_id == entity_id, Emission.year == base_year,
            Emission.scenario_id.is_(None))
    ) or 0.0
    pathway = service.sbti_pathway(base_year, float(base_kg) / 1000, target_year, ambition)
    actual = db.execute(
        select(Emission.year, func.sum(Emission.co2e_kg))
        .where(Emission.entity_id == entity_id, Emission.scenario_id.is_(None))
        .group_by(Emission.year).order_by(Emission.year)
    ).all()
    actuals = {int(r[0]): round(float(r[1]) / 1000, 3) for r in actual}
    for point in pathway["pathway"]:
        point["actual_tco2e"] = actuals.get(point["year"])
        if point["actual_tco2e"] is not None:
            point["variance_tco2e"] = round(
                point["actual_tco2e"] - point["allowed_tco2e"], 3)
            point["on_track"] = point["actual_tco2e"] <= point["allowed_tco2e"]
    return {**pathway, "entity_id": entity_id,
            "ambitions_available": list(service.SBTI_ANNUAL_LINEAR_REDUCTION.keys())}


# ---------------------------------------------------------------------------
# FR-3.D.3  Hotspots, levers, MACC, roadmap, ROI, progress
# ---------------------------------------------------------------------------

@router.get("/hotspots/pareto")
def pareto(entity_id: int | None = None, year: int | None = None,
           dimension: str = Query(default="category",
                                  pattern="^(category|facility|supplier|scope|entity)$"),
           db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.D.3 - hotspot Pareto analysis."""
    return service.pareto_hotspots(db, entity_id=entity_id, year=year, dimension=dimension)


@router.get("/levers")
def list_levers(entity_id: int | None = None, status: str | None = None,
                db: Session = Depends(get_db), p: Principal = Depends(get_principal),
                ctx: ScenarioContext = Depends(get_scenario_context)):
    stmt = select(ReductionInitiative).order_by(ReductionInitiative.investment_priority)
    if entity_id:
        stmt = stmt.where(ReductionInitiative.entity_id == entity_id)
    if status:
        stmt = stmt.where(ReductionInitiative.status == status)
    stmt = ctx.filter(scoped(stmt, ReductionInitiative, p), ReductionInitiative)
    return rows(db.scalars(stmt))


class LeverIn(BaseModel):
    entity_id: int
    facility_id: int | None = None
    supplier_id: int | None = None
    name: str
    lever_category: str
    scope: str
    description: str = ""
    start_year: int = date.today().year
    end_year: int = date.today().year + 5
    capex: float = 0.0
    annual_opex_delta: float = 0.0
    annual_abatement_tco2e: float = 0.0
    lifetime_years: int = 10
    technology_readiness: str = "mature"
    status: str = "proposed"


@router.post("/levers", status_code=201)
def create_lever(payload: LeverIn, db: Session = Depends(get_db),
                 p: Principal = Depends(require("analytics.write")),
                 ctx: ScenarioContext = Depends(get_scenario_context)):
    lever = ReductionInitiative(**payload.model_dump())
    ctx.stamp(lever)
    try:
        guard_scenario_write(ctx, lever)
    except ScenarioIsolationError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add(lever)
    db.commit()
    return to_dict(lever)


@router.patch("/levers/{lever_id}")
def update_lever(lever_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                 p: Principal = Depends(require("analytics.write"))):
    lever = db.get(ReductionInitiative, lever_id)
    if lever is None:
        raise HTTPException(404, "Reduction initiative not found")
    for k, v in payload.items():
        if hasattr(lever, k) and k not in ("id", "scenario_id"):
            setattr(lever, k, v)
    db.commit()
    return to_dict(lever)


@router.get("/macc")
def macc(entity_id: int | None = None, db: Session = Depends(get_db),
         p: Principal = Depends(get_principal),
         ctx: ScenarioContext = Depends(get_scenario_context)):
    """FR-3.D.3 - marginal abatement cost curve, investment priority and ROI."""
    result = service.build_macc(db, entity_id=entity_id, scenario_id=ctx.scenario_id)
    db.commit()
    return result


@router.get("/roadmap")
def roadmap(entity_id: int, horizon_year: int = 2040, db: Session = Depends(get_db),
            p: Principal = Depends(get_principal)):
    """FR-3.D.3 - technology roadmap."""
    return service.technology_roadmap(db, entity_id=entity_id, horizon_year=horizon_year)


@router.get("/progress")
def progress_tracking(entity_id: int, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    """FR-3.D.3 - progress tracking against planned abatement."""
    initiatives = list(db.scalars(select(ReductionInitiative).where(
        ReductionInitiative.entity_id == entity_id,
        ReductionInitiative.scenario_id.is_(None))))
    planned = sum(i.annual_abatement_tco2e or 0.0 for i in initiatives)
    realized = sum(i.realized_abatement_tco2e or 0.0 for i in initiatives)
    by_status: dict[str, int] = {}
    for i in initiatives:
        by_status[i.status] = by_status.get(i.status, 0) + 1
    return {
        "entity_id": entity_id,
        "initiative_count": len(initiatives),
        "planned_annual_abatement_tco2e": round(planned, 3),
        "realized_annual_abatement_tco2e": round(realized, 3),
        "delivery_pct": round(realized / planned * 100, 1) if planned else 0.0,
        "by_status": by_status,
        "initiatives": [
            {"id": i.id, "name": i.name, "status": i.status,
             "progress_pct": i.progress_pct,
             "planned_tco2e": i.annual_abatement_tco2e,
             "realized_tco2e": i.realized_abatement_tco2e,
             "variance_tco2e": round(
                 (i.realized_abatement_tco2e or 0) - (i.annual_abatement_tco2e or 0), 3),
             "roi_pct": i.roi_pct, "payback_years": i.payback_years,
             "investment_priority": i.investment_priority}
            for i in sorted(initiatives, key=lambda x: x.investment_priority or 999)
        ],
    }


# ---------------------------------------------------------------------------
# FR-3.D.4  Data quality, factor confidence, lineage, versions, change history
# ---------------------------------------------------------------------------

@router.get("/data-quality/scores")
def data_quality_scores(entity_id: int | None = None, year: int | None = None,
                        db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.D.4 / FR-7.4 - the data-quality picture for a reporting period."""
    stmt = select(Emission).where(Emission.scenario_id.is_(None))
    if entity_id:
        stmt = stmt.where(Emission.entity_id == entity_id)
    if year:
        stmt = stmt.where(Emission.year == year)
    emissions = list(db.scalars(scoped(stmt, Emission, p)))
    if not emissions:
        return {"entity_id": entity_id, "year": year, "record_count": 0,
                "message": "No emissions in scope."}

    total_kg = sum(e.co2e_kg for e in emissions)
    by_rating: dict[str, dict] = {}
    for e in emissions:
        band = by_rating.setdefault(e.data_quality_rating or "unrated",
                                    {"rating": e.data_quality_rating or "unrated",
                                     "count": 0, "tco2e": 0.0})
        band["count"] += 1
        band["tco2e"] += e.co2e_kg / 1000

    estimated_kg = sum(e.co2e_kg for e in emissions if e.is_estimated)
    calcs = [db.get(Calculation, e.calculation_id) for e in emissions]
    calcs = [c for c in calcs if c is not None]
    factor_confidence = (
        sum(100 - (db.get(EmissionFactor, c.emission_factor_id).uncertainty_pct
                   if db.get(EmissionFactor, c.emission_factor_id) else 50)
            for c in calcs) / len(calcs)
    ) if calcs else 0.0

    origins: dict[str, float] = {}
    for c in calcs:
        act = db.get(ActivityData, c.activity_data_id)
        if act:
            origins[act.data_origin] = origins.get(act.data_origin, 0.0) + c.consolidated_co2e_kg

    return {
        "entity_id": entity_id, "year": year,
        "record_count": len(emissions),
        "total_tco2e": round(total_kg / 1000, 3),
        "average_confidence_score": round(
            sum(e.confidence_score for e in emissions) / len(emissions), 2),
        "average_factor_confidence": round(factor_confidence, 2),
        "completeness_pct": round(
            sum(1 for e in emissions if not e.is_estimated) / len(emissions) * 100, 1),
        "estimated_share_pct": round(estimated_kg / total_kg * 100, 2) if total_kg else 0.0,
        "by_rating": sorted(
            [{**b, "tco2e": round(b["tco2e"], 3),
              "share_pct": round(b["tco2e"] * 1000 / total_kg * 100, 2) if total_kg else 0.0}
             for b in by_rating.values()],
            key=lambda b: b["rating"]),
        "by_data_origin": sorted(
            [{"data_origin": k, "tco2e": round(v / 1000, 3),
              "share_pct": round(v / total_kg * 100, 2) if total_kg else 0.0}
             for k, v in origins.items()],
            key=lambda d: -d["tco2e"]),
        "open_anomalies": db.scalar(select(func.count()).select_from(Anomaly)
                                    .where(Anomaly.status == "open")) or 0,
        "open_gaps": db.scalar(select(func.count()).select_from(DataGap)
                               .where(DataGap.status == "open")) or 0,
        "pedigree_model": "ecoinvent-style pedigree matrix combined in quadrature",
    }


@router.get("/calculation-versions")
def calculation_versions(activity_data_id: int, db: Session = Depends(get_db),
                         p: Principal = Depends(get_principal)):
    """FR-3.D.4 - calculation versions and change history for one input."""
    calcs = db.scalars(select(Calculation)
                       .where(Calculation.activity_data_id == activity_data_id)
                       .order_by(Calculation.version)).all()
    history = []
    for c in calcs:
        changes = db.scalars(select(AuditLog).where(
            AuditLog.object_type == "calculation", AuditLog.object_id == c.id)
            .order_by(AuditLog.at)).all()
        approvals = db.scalars(select(Approval).where(
            Approval.object_type == "calculation", Approval.object_id == c.id)).all()
        history.append({
            "calculation_id": c.id, "version": c.version, "status": c.status,
            "co2e_kg": c.co2e_kg, "consolidated_co2e_kg": c.consolidated_co2e_kg,
            "factor_library_version": c.factor_library_version,
            "method_version": c.method_version, "gwp_set": c.gwp_set,
            "supersedes_id": c.supersedes_id,
            "restatement_reason": c.restatement_reason,
            "confidence_score": c.confidence_score,
            "data_quality_rating": c.data_quality_rating,
            "created_at": c.created_at.isoformat(),
            "approvals": rows(approvals),
            "changes": rows(changes),
        })
    return {"activity_data_id": activity_data_id, "version_count": len(calcs),
            "versions": history}


@router.get("/change-history")
def change_history(object_type: str | None = None, object_id: int | None = None,
                   action: str | None = None, page: int = 1, page_size: int = 100,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.D.4 / FR-7.2 - the timestamped change log."""
    stmt = select(AuditLog).order_by(AuditLog.at.desc())
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return page_response(db, stmt, page=page, page_size=page_size)


@router.post("/data-quality/validate")
def run_validation(entity_id: int = Body(...), year: int = Body(default=date.today().year),
                   db: Session = Depends(get_db),
                   p: Principal = Depends(require("analytics.write"))):
    """FR-7.4 - validation/cleansing pass producing remediation-ready findings."""
    activities = list(db.scalars(select(ActivityData).where(
        ActivityData.entity_id == entity_id,
        ActivityData.period_start >= date(year, 1, 1),
        ActivityData.period_start <= date(year, 12, 31),
        ActivityData.scenario_id.is_(None))))
    findings = []
    for a in activities:
        messages = []
        if a.quantity <= 0:
            messages.append({"rule": "positive_quantity",
                             "message": "Quantity must be greater than zero",
                             "severity": "error"})
        if a.period_end < a.period_start:
            messages.append({"rule": "period_order",
                             "message": "Period end precedes period start",
                             "severity": "error"})
        if a.evidence_status == "missing" and a.data_origin not in ("meter", "sensor",
                                                                   "telematics"):
            messages.append({"rule": "evidence_required",
                             "message": "No supporting evidence attached",
                             "severity": "warning"})
        if a.completeness_pct < 90:
            messages.append({"rule": "completeness",
                             "message": f"Completeness is {a.completeness_pct:g}%",
                             "severity": "warning"})
        if not messages:
            continue
        calc = db.scalars(select(Calculation)
                          .where(Calculation.activity_data_id == a.id)).first()
        assessment = db.scalars(select(DataQualityAssessment).where(
            DataQualityAssessment.object_type == "activity_data",
            DataQualityAssessment.object_id == a.id)).first()
        if assessment is None:
            assessment = DataQualityAssessment(
                object_type="activity_data", object_id=a.id,
                entity_id=a.entity_id, scope=a.scope, period_year=year)
            db.add(assessment)
        assessment.completeness_pct = a.completeness_pct
        assessment.validation_passed = not any(m["severity"] == "error" for m in messages)
        assessment.validation_messages = messages
        assessment.is_estimated = a.is_estimated
        assessment.evidence_status = a.evidence_status
        assessment.uncertainty_pct = calc.uncertainty_pct if calc else 0.0
        assessment.confidence_score = calc.confidence_score if calc else 0.0
        assessment.rating = calc.data_quality_rating if calc else "unrated"
        findings.append({
            "activity_data_id": a.id, "activity_key": a.activity_key,
            "description": a.description, "messages": messages,
            "validation_passed": assessment.validation_passed,
        })
    db.commit()
    return {
        "entity_id": entity_id, "year": year,
        "examined": len(activities), "with_findings": len(findings),
        "errors": sum(1 for f in findings
                      if any(m["severity"] == "error" for m in f["messages"])),
        "warnings": sum(1 for f in findings
                        if all(m["severity"] != "error" for m in f["messages"])),
        "findings": findings[:200],
    }


@router.get("/data-quality/assessments")
def list_assessments(entity_id: int | None = None, year: int | None = None,
                     passed: bool | None = None, page: int = 1, page_size: int = 50,
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(DataQualityAssessment).order_by(DataQualityAssessment.confidence_score)
    if entity_id:
        stmt = stmt.where(DataQualityAssessment.entity_id == entity_id)
    if year:
        stmt = stmt.where(DataQualityAssessment.period_year == year)
    if passed is not None:
        stmt = stmt.where(DataQualityAssessment.validation_passed.is_(passed))
    return page_response(db, scoped(stmt, DataQualityAssessment, p),
                         page=page, page_size=page_size)
