"""A) Enterprise Carbon Accounting - FR-3.A.1 to FR-3.A.5."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import (
    ScenarioContext, ScenarioIsolationError, assert_visible, get_scenario_context,
    guard_scenario_write, scoped,
)
from app.core.serialize import kg_to_t, page_response, rows, to_dict
from app.domain.enums import (
    SCOPE3_CATEGORIES, SCOPE3_DATA_METHODS, CalculationStatus, ConsolidationMethod,
    DataOrigin, Scope, Scope1Source, Scope2Method,
)
from app.domain.models import (
    ActivityData, Baseline, Calculation, Category, CostCenter, Department, Emission,
    EmissionFactor, Entity, Facility, FactorLibrary, Intensity, MeterReading,
    Organization, ReportingBoundary, Source, Target, Transaction,
)
from app.engine import consolidation, factors as factor_engine, gwp, lineage, recalc, units
from app.engine.allocation import AllocationTarget, available_bases
from app.engine.calculator import (
    CalculationOptions, LockedPeriodError, approve as approve_calc, calculate,
    calculate_batch, lock as lock_calc, reproduce,
)

router = APIRouter(prefix="/accounting", tags=["A) Enterprise Carbon Accounting"])


# ---------------------------------------------------------------------------
# FR-3.A.5  Organization model
# ---------------------------------------------------------------------------

@router.get("/organizations")
def list_organizations(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Organization).order_by(Organization.name)
    if not p.is_unrestricted:
        stmt = stmt.where(Organization.id.in_(p.organization_ids or {0}))
    return rows(db.scalars(stmt))


@router.get("/entities")
def list_entities(
    organization_id: int | None = None,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    stmt = select(Entity).order_by(Entity.name)
    if organization_id:
        stmt = stmt.where(Entity.organization_id == organization_id)
    stmt = scoped(stmt, Entity, p)
    return rows(db.scalars(stmt))


@router.get("/entities/tree")
def entity_tree(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """The organization hierarchy with ownership controls (FR-3.A.5)."""
    stmt = scoped(select(Entity).order_by(Entity.name), Entity, p)
    entities = list(db.scalars(stmt))
    by_id = {e.id: {**to_dict(e), "children": [], "facilities": []} for e in entities}
    for e in entities:
        facs = db.scalars(select(Facility).where(Facility.entity_id == e.id)).all()
        by_id[e.id]["facilities"] = rows(facs)
    roots = []
    for e in entities:
        node = by_id[e.id]
        if e.parent_id and e.parent_id in by_id:
            by_id[e.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.get("/entities/{entity_id}/ownership")
def entity_ownership(
    entity_id: int,
    method: str = Query(default=ConsolidationMethod.OPERATIONAL_CONTROL),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    assert_visible(p, object_type="entity", object_id=entity_id)
    result = consolidation.ownership_share(db, entity_id, method)
    return {
        "entity_id": entity_id, "method": result.method, "share": result.share,
        "explanation": result.explanation, "ownership_path": result.path,
        "descendants": consolidation.descendant_entity_ids(db, entity_id),
    }


@router.get("/facilities")
def list_facilities(
    entity_id: int | None = None, page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Facility).order_by(Facility.name)
    if entity_id:
        stmt = stmt.where(Facility.entity_id == entity_id)
    return page_response(db, scoped(stmt, Facility, p), page=page, page_size=page_size)


@router.get("/departments")
def list_departments(entity_id: int | None = None, db: Session = Depends(get_db),
                     p: Principal = Depends(get_principal)):
    stmt = select(Department).order_by(Department.name)
    if entity_id:
        stmt = stmt.where(Department.entity_id == entity_id)
    return rows(db.scalars(scoped(stmt, Department, p)))


@router.get("/cost-centers")
def list_cost_centers(entity_id: int | None = None, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    stmt = select(CostCenter).order_by(CostCenter.code)
    if entity_id:
        stmt = stmt.where(CostCenter.entity_id == entity_id)
    return rows(db.scalars(scoped(stmt, CostCenter, p)))


@router.get("/reporting-boundaries")
def list_boundaries(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(ReportingBoundary)
    return rows(db.scalars(scoped(stmt, ReportingBoundary, p)))


class BoundaryIn(BaseModel):
    organization_id: int
    name: str
    consolidation_method: str = ConsolidationMethod.OPERATIONAL_CONTROL
    baseline_year: int = 2020
    included_entity_ids: list[int] = Field(default_factory=list)
    scopes_covered: list[str] = Field(default_factory=lambda: [s.value for s in Scope])
    description: str = ""


@router.post("/reporting-boundaries", status_code=201)
def create_boundary(payload: BoundaryIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("accounting.write"))):
    b = ReportingBoundary(**payload.model_dump())
    db.add(b)
    db.commit()
    lineage.record_change(db, action="create", object_type="reporting_boundary",
                          object_id=b.id, user_id=p.user.id, user_email=p.user.email,
                          after=to_dict(b))
    db.commit()
    return to_dict(b)


@router.get("/baselines")
def list_baselines(entity_id: int | None = None, db: Session = Depends(get_db),
                   p: Principal = Depends(get_principal)):
    stmt = select(Baseline).order_by(Baseline.year)
    if entity_id:
        stmt = stmt.where(Baseline.entity_id == entity_id)
    return rows(db.scalars(scoped(stmt, Baseline, p)))


@router.post("/baselines/recalculate")
def recalculate_baseline(
    entity_id: int = Body(...), year: int = Body(...), reason: str = Body(...),
    db: Session = Depends(get_db), p: Principal = Depends(require("accounting.approve")),
):
    """FR-3.A.5 / FR-7.3 - baseline recalculation with a documented reason."""
    result = recalc.recalculate_baseline(db, entity_id=entity_id, year=year,
                                         reason=reason, user_id=p.user.id)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@router.get("/categories")
def list_categories(scope: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Category).order_by(Category.scope, Category.number)
    if scope:
        stmt = stmt.where(Category.scope == scope)
    return rows(db.scalars(stmt))


@router.get("/sources")
def list_sources(entity_id: int | None = None, scope: str | None = None,
                 db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Source).order_by(Source.name)
    if entity_id:
        stmt = stmt.where(Source.entity_id == entity_id)
    if scope:
        stmt = stmt.where(Source.scope == scope)
    return rows(db.scalars(scoped(stmt, Source, p)))


@router.get("/reference/vocabulary")
def vocabulary():
    """The controlled vocabulary the UI renders from - FR-3.A.1/.2/.3."""
    return {
        "scopes": [s.value for s in Scope],
        "scope1_sources": [s.value for s in Scope1Source],
        "scope2_methods": [m.value for m in Scope2Method],
        "scope3_categories": [{"number": n, "name": v} for n, v in SCOPE3_CATEGORIES.items()],
        "scope3_data_methods": SCOPE3_DATA_METHODS,
        "data_origins": [d.value for d in DataOrigin],
        "consolidation_methods": [c.value for c in ConsolidationMethod],
        "allocation_bases": available_bases(),
        "gwp_sets": gwp.available_sets(),
        "units": units.known_units(),
        "calculation_statuses": [s.value for s in CalculationStatus],
    }


# ---------------------------------------------------------------------------
# FR-3.A.1 / .2 / .3  Activity data capture
# ---------------------------------------------------------------------------

def _activity_extra(db: Session, a: ActivityData) -> dict:
    ent = db.get(Entity, a.entity_id)
    fac = db.get(Facility, a.facility_id) if a.facility_id else None
    cat = db.get(Category, a.category_id) if a.category_id else None
    calc = db.scalars(
        select(Calculation).where(Calculation.activity_data_id == a.id)
        .order_by(Calculation.version.desc())
    ).first()
    return {
        "entity_name": ent.name if ent else None,
        "facility_name": fac.name if fac else None,
        "category_name": cat.name if cat else None,
        "category_number": cat.number if cat else None,
        "calculation_id": calc.id if calc else None,
        "co2e_kg": calc.consolidated_co2e_kg if calc else None,
        "co2e_tonnes": kg_to_t(calc.consolidated_co2e_kg) if calc else None,
        "calculation_status": calc.status if calc else "not_calculated",
        "data_quality_rating": calc.data_quality_rating if calc else None,
        "confidence_score": calc.confidence_score if calc else None,
    }


@router.get("/activity-data")
def list_activity_data(
    scope: str | None = None,
    entity_id: int | None = None,
    facility_id: int | None = None,
    supplier_id: int | None = None,
    product_id: int | None = None,
    category_id: int | None = None,
    category_number: int | None = None,
    year: int | None = None,
    data_origin: str | None = None,
    source_type: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    stmt = select(ActivityData).order_by(ActivityData.period_start.desc(), ActivityData.id.desc())
    if scope:
        stmt = stmt.where(ActivityData.scope == scope)
    if entity_id:
        stmt = stmt.where(ActivityData.entity_id == entity_id)
    if facility_id:
        stmt = stmt.where(ActivityData.facility_id == facility_id)
    if supplier_id:
        stmt = stmt.where(ActivityData.supplier_id == supplier_id)
    if product_id:
        stmt = stmt.where(ActivityData.product_id == product_id)
    if category_id:
        stmt = stmt.where(ActivityData.category_id == category_id)
    if category_number:
        cat = db.scalars(select(Category).where(Category.number == category_number,
                                                Category.scope == Scope.SCOPE_3)).first()
        stmt = stmt.where(ActivityData.category_id == (cat.id if cat else -1))
    if year:
        stmt = stmt.where(ActivityData.period_start >= date(year, 1, 1),
                          ActivityData.period_start <= date(year, 12, 31))
    if data_origin:
        stmt = stmt.where(ActivityData.data_origin == data_origin)
    if source_type:
        stmt = stmt.where(ActivityData.activity_key.like(f"{source_type}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(ActivityData.description.like(like) | ActivityData.activity_key.like(like))
    stmt = ctx.filter(scoped(stmt, ActivityData, p), ActivityData)
    return page_response(db, stmt, page=page, page_size=page_size,
                         mapper=lambda a: to_dict(a, extra=_activity_extra(db, a)))


class ActivityIn(BaseModel):
    entity_id: int
    facility_id: int | None = None
    department_id: int | None = None
    cost_center_id: int | None = None
    source_id: int | None = None
    supplier_id: int | None = None
    product_id: int | None = None
    category_id: int | None = None
    scope: str
    activity_key: str
    description: str = ""
    quantity: float
    unit: str
    period_start: date
    period_end: date
    data_origin: str = DataOrigin.ESTIMATED
    scope3_method: str | None = None
    scope2_method: str | None = None
    is_estimated: bool = False
    completeness_pct: float = 100.0
    evidence_status: str = "missing"
    notes: str = ""
    external_ref: str = ""


@router.post("/activity-data", status_code=201)
def create_activity_data(
    payload: ActivityIn,
    calculate_now: bool = Query(default=True),
    db: Session = Depends(get_db),
    p: Principal = Depends(require("accounting.write")),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    assert_visible(p, object_type="entity", object_id=payload.entity_id)
    a = ActivityData(**payload.model_dump())
    ctx.stamp(a)
    try:
        guard_scenario_write(ctx, a)
    except ScenarioIsolationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.add(a)
    db.flush()
    lineage.record_change(db, action="create", object_type="activity_data", object_id=a.id,
                          user_id=p.user.id, user_email=p.user.email, after=to_dict(a))
    result = None
    if calculate_now:
        try:
            res = calculate(db, a, CalculationOptions(scenario_id=ctx.scenario_id))
            result = {"calculation_id": res.calculation.id,
                      "co2e_kg": res.calculation.consolidated_co2e_kg,
                      "formula": res.calculation.formula,
                      "warnings": res.warnings}
        except Exception as exc:
            result = {"error": str(exc)}
    db.commit()
    return {**to_dict(a), "calculation": result}


@router.patch("/activity-data/{activity_id}")
def update_activity_data(
    activity_id: int, payload: dict = Body(...),
    db: Session = Depends(get_db),
    p: Principal = Depends(require("accounting.write")),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    a = db.get(ActivityData, activity_id)
    if a is None:
        raise HTTPException(404, "Activity data not found")
    assert_visible(p, object_type="entity", object_id=a.entity_id)
    # FR-7.3: an approved/locked calculation makes its input immutable.
    calc = db.scalars(select(Calculation).where(Calculation.activity_data_id == a.id)).all()
    if any(c.status in (CalculationStatus.APPROVED, CalculationStatus.LOCKED) for c in calc):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This activity feeds an approved value. Restate the calculation instead (FR-7.3).",
        )
    before = to_dict(a)
    for k, v in payload.items():
        if hasattr(a, k) and k not in ("id", "scenario_id"):
            setattr(a, k, v)
    lineage.record_change(db, action="update", object_type="activity_data", object_id=a.id,
                          user_id=p.user.id, user_email=p.user.email,
                          before=before, after=to_dict(a))
    db.commit()
    return to_dict(a)


# --- FR-3.A.1 meter / sensor / telematics capture --------------------------

@router.get("/meter-readings")
def list_meter_readings(
    facility_id: int | None = None, meter_type: str | None = None,
    capture_method: str | None = None, page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(MeterReading).order_by(MeterReading.reading_at.desc())
    if facility_id:
        stmt = stmt.where(MeterReading.facility_id == facility_id)
    if meter_type:
        stmt = stmt.where(MeterReading.meter_type == meter_type)
    if capture_method:
        stmt = stmt.where(MeterReading.capture_method == capture_method)
    return page_response(db, scoped(stmt, MeterReading, p), page=page, page_size=page_size)


@router.post("/meter-readings", status_code=201)
def create_meter_reading(payload: dict = Body(...), db: Session = Depends(get_db),
                         p: Principal = Depends(require("accounting.write"))):
    m = MeterReading(**payload)
    db.add(m)
    db.commit()
    return to_dict(m)


@router.get("/transactions")
def list_transactions(
    entity_id: int | None = None, supplier_id: int | None = None,
    uncategorized_only: bool = False, page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Transaction).order_by(Transaction.transaction_date.desc())
    if entity_id:
        stmt = stmt.where(Transaction.entity_id == entity_id)
    if supplier_id:
        stmt = stmt.where(Transaction.supplier_id == supplier_id)
    if uncategorized_only:
        stmt = stmt.where(Transaction.category_id.is_(None))
    return page_response(db, scoped(stmt, Transaction, p), page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Factor libraries (FR-5.3, FR-7.3)
# ---------------------------------------------------------------------------

@router.get("/factor-libraries")
def list_factor_libraries(db: Session = Depends(get_db)):
    libs = db.scalars(select(FactorLibrary).order_by(FactorLibrary.provider)).all()
    out = []
    for lib in libs:
        count = db.scalar(select(func.count()).select_from(EmissionFactor)
                          .where(EmissionFactor.library_id == lib.id))
        out.append({**to_dict(lib), "factor_count": count})
    return out


@router.post("/factor-libraries/{library_id}/lock")
def lock_library(library_id: int, locked: bool = Body(default=True, embed=True),
                 db: Session = Depends(get_db),
                 p: Principal = Depends(require("accounting.approve"))):
    """FR-7.3 - methodology/version locking."""
    lib = db.get(FactorLibrary, library_id)
    if lib is None:
        raise HTTPException(404, "Factor library not found")
    before = {"is_locked": lib.is_locked}
    lib.is_locked = locked
    lineage.record_change(db, action="lock_library", object_type="factor_library",
                          object_id=lib.id, user_id=p.user.id, user_email=p.user.email,
                          before=before, after={"is_locked": locked},
                          reason="Period close - factor version locked")
    db.commit()
    return to_dict(lib)


@router.get("/emission-factors")
def list_emission_factors(
    activity_key: str | None = None, country: str | None = None,
    library_id: int | None = None, scope: str | None = None,
    q: str | None = None, page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db),
):
    stmt = select(EmissionFactor).order_by(EmissionFactor.activity_key, EmissionFactor.country)
    if activity_key:
        stmt = stmt.where(EmissionFactor.activity_key == activity_key)
    if country:
        stmt = stmt.where(EmissionFactor.country == country)
    if library_id:
        stmt = stmt.where(EmissionFactor.library_id == library_id)
    if scope:
        stmt = stmt.where(EmissionFactor.scope == scope)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(EmissionFactor.name.like(like) | EmissionFactor.activity_key.like(like))
    return page_response(db, stmt, page=page, page_size=page_size)


@router.get("/emission-factors/resolve")
def resolve_factor(
    activity_key: str, country: str = "GLOBAL",
    period: date = Query(default_factory=date.today),
    method: str | None = None, library_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Explainable factor selection - shows why this factor won (FR-3.A.4)."""
    try:
        match = factor_engine.resolve(db, activity_key=activity_key, country=country,
                                      period=period, method=method, library_id=library_id)
    except factor_engine.FactorNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "selected": {**to_dict(match.factor), "score": match.score, "reasons": match.reasons},
        "alternatives": factor_engine.alternatives(
            db, activity_key=activity_key, country=country, period=period,
            method=method, library_id=library_id, limit=5),
    }


@router.get("/grid-factors/countries")
def grid_factor_countries(db: Session = Depends(get_db)):
    """FR-3.A.2 - grid factors for 150+ countries."""
    rows_ = db.execute(
        select(EmissionFactor.country, func.count(EmissionFactor.id),
               func.min(EmissionFactor.value_kgco2e), func.max(EmissionFactor.value_kgco2e))
        .where(EmissionFactor.activity_key.like("electricity.grid%"))
        .group_by(EmissionFactor.country)
        .order_by(EmissionFactor.country)
    ).all()
    return {
        "country_count": len(rows_),
        "countries": [
            {"country": r[0], "factor_count": r[1],
             "min_kgco2e_per_kwh": round(r[2], 5), "max_kgco2e_per_kwh": round(r[3], 5)}
            for r in rows_
        ],
    }


# ---------------------------------------------------------------------------
# FR-3.A.4  The calculation engine
# ---------------------------------------------------------------------------

class CalculateIn(BaseModel):
    activity_data_ids: list[int] = Field(default_factory=list)
    gwp_set: str | None = None
    method_version: str | None = None
    library_id: int | None = None
    consolidation_method: str | None = None
    allocation_basis: str = "mass"
    allocation_targets: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


@router.post("/calculations/run")
def run_calculation(
    payload: CalculateIn,
    db: Session = Depends(get_db),
    p: Principal = Depends(require("accounting.write")),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    """Run the engine over specific activity rows, or everything uncalculated."""
    stmt = select(ActivityData)
    if payload.activity_data_ids:
        stmt = stmt.where(ActivityData.id.in_(payload.activity_data_ids))
    else:
        done = select(Calculation.activity_data_id).where(
            Calculation.scenario_id.is_(None) if ctx.scenario_id is None
            else Calculation.scenario_id == ctx.scenario_id
        )
        stmt = stmt.where(ActivityData.id.not_in(done))
    stmt = ctx.filter(scoped(stmt, ActivityData, p), ActivityData)
    activities = list(db.scalars(stmt))

    opts = CalculationOptions(
        gwp_set=payload.gwp_set or CalculationOptions().gwp_set,
        method_version=payload.method_version or CalculationOptions().method_version,
        library_id=payload.library_id,
        consolidation_method=payload.consolidation_method,
        allocation_basis=payload.allocation_basis,
        allocation_targets=[
            AllocationTarget(t.get("target_type", "entity"), int(t["target_id"]),
                             float(t.get("basis_value", 1.0)), t.get("label", ""))
            for t in payload.allocation_targets
        ],
        scenario_id=ctx.scenario_id,
        assumptions=payload.assumptions,
    )
    result = calculate_batch(db, activities, opts)
    db.commit()
    return {**result, "scenario_id": ctx.scenario_id,
            "is_sandbox": ctx.is_sandbox, "considered": len(activities)}


def _calc_extra(db: Session, c: Calculation) -> dict:
    act = db.get(ActivityData, c.activity_data_id)
    ent = db.get(Entity, act.entity_id) if act else None
    fac = db.get(Facility, act.facility_id) if act and act.facility_id else None
    return {
        "activity_key": act.activity_key if act else None,
        "activity_description": act.description if act else None,
        "scope": act.scope if act else None,
        "period_start": act.period_start.isoformat() if act else None,
        "entity_name": ent.name if ent else None,
        "facility_name": fac.name if fac else None,
        "co2e_tonnes": kg_to_t(c.consolidated_co2e_kg),
    }


@router.get("/calculations")
def list_calculations(
    status_filter: str | None = Query(default=None, alias="status"),
    entity_id: int | None = None, scope: str | None = None,
    year: int | None = None, page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    stmt = select(Calculation).order_by(Calculation.id.desc())
    if status_filter:
        stmt = stmt.where(Calculation.status == status_filter)
    if entity_id or scope or year:
        sub = select(ActivityData.id)
        if entity_id:
            sub = sub.where(ActivityData.entity_id == entity_id)
        if scope:
            sub = sub.where(ActivityData.scope == scope)
        if year:
            sub = sub.where(ActivityData.period_start >= date(year, 1, 1),
                            ActivityData.period_start <= date(year, 12, 31))
        stmt = stmt.where(Calculation.activity_data_id.in_(sub))
    stmt = ctx.filter(stmt, Calculation)
    return page_response(db, stmt, page=page, page_size=page_size,
                         mapper=lambda c: to_dict(c, exclude={"lineage"},
                                                  extra=_calc_extra(db, c)))


@router.get("/calculations/{calculation_id}")
def get_calculation(calculation_id: int, db: Session = Depends(get_db),
                    p: Principal = Depends(get_principal)):
    c = db.get(Calculation, calculation_id)
    if c is None:
        raise HTTPException(404, "Calculation not found")
    return to_dict(c, extra=_calc_extra(db, c))


@router.get("/calculations/{calculation_id}/lineage")
def calculation_lineage(calculation_id: int, db: Session = Depends(get_db),
                        p: Principal = Depends(get_principal)):
    """FR-7.2 - the complete audit trail behind one number."""
    try:
        return lineage.read(db, calculation_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/calculations/{calculation_id}/reproduce")
def reproduce_calculation(calculation_id: int, db: Session = Depends(get_db),
                          p: Principal = Depends(get_principal)):
    """FR-7.3 reproducibility check."""
    c = db.get(Calculation, calculation_id)
    if c is None:
        raise HTTPException(404, "Calculation not found")
    return reproduce(db, c)


@router.post("/calculations/{calculation_id}/approve")
def approve_calculation(calculation_id: int, comment: str = Body(default="", embed=True),
                        db: Session = Depends(get_db),
                        p: Principal = Depends(require("accounting.approve"))):
    c = db.get(Calculation, calculation_id)
    if c is None:
        raise HTTPException(404, "Calculation not found")
    if c.scenario_id is not None:
        raise HTTPException(409, "Scenario results cannot be approved as actuals (FR-7.8)")
    try:
        approve_calc(db, c, user_id=p.user.id, user_email=p.user.email, comment=comment)
    except LockedPeriodError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return to_dict(c, exclude={"lineage"})


@router.post("/calculations/{calculation_id}/lock")
def lock_calculation(calculation_id: int, reason: str = Body(default="Period close", embed=True),
                     db: Session = Depends(get_db),
                     p: Principal = Depends(require("accounting.approve"))):
    c = db.get(Calculation, calculation_id)
    if c is None:
        raise HTTPException(404, "Calculation not found")
    try:
        lock_calc(db, c, user_id=p.user.id, user_email=p.user.email, reason=reason)
    except LockedPeriodError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return to_dict(c, exclude={"lineage"})


# --- FR-7.3 recalculation impact & restatement -----------------------------

@router.post("/recalculation/impact")
def recalculation_impact(
    new_library_id: int | None = Body(default=None),
    new_gwp_set: str | None = Body(default=None),
    new_method_version: str | None = Body(default=None),
    entity_id: int | None = Body(default=None),
    year: int | None = Body(default=None),
    db: Session = Depends(get_db),
    p: Principal = Depends(require("accounting.approve")),
):
    """Dry run - shows exactly what would change, and changes nothing."""
    return recalc.impact_analysis(
        db, new_library_id=new_library_id, new_gwp_set=new_gwp_set,
        new_method_version=new_method_version, entity_id=entity_id, year=year,
    )


@router.post("/recalculation/restate")
def restate(
    calculation_ids: list[int] = Body(...),
    reason: str = Body(...),
    new_library_id: int | None = Body(default=None),
    new_gwp_set: str | None = Body(default=None),
    new_method_version: str | None = Body(default=None),
    allow_locked: bool = Body(default=False),
    db: Session = Depends(get_db),
    p: Principal = Depends(require("accounting.approve")),
):
    try:
        result = recalc.restate(
            db, calculation_ids=calculation_ids, reason=reason,
            new_library_id=new_library_id, new_gwp_set=new_gwp_set,
            new_method_version=new_method_version,
            user_id=p.user.id, user_email=p.user.email, allow_locked=allow_locked,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Scope summaries (FR-3.A.1 / .2 / .3)
# ---------------------------------------------------------------------------

def _emission_query(p: Principal, ctx: ScenarioContext, **filters):
    stmt = select(Emission)
    for key, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(Emission, key) == value)
    return ctx.filter(scoped(stmt, Emission, p), Emission)


@router.get("/scope1/summary")
def scope1_summary(year: int | None = None, entity_id: int | None = None,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal),
                   ctx: ScenarioContext = Depends(get_scenario_context)):
    """FR-3.A.1 - by the five named source types."""
    stmt = _emission_query(p, ctx, scope=Scope.SCOPE_1, year=year, entity_id=entity_id)
    ems = list(db.scalars(stmt))
    by_type: dict[str, float] = {}
    by_capture: dict[str, float] = {}
    for e in ems:
        act = db.get(ActivityData, db.get(Calculation, e.calculation_id).activity_data_id)
        src_type = (act.activity_key.split(".")[0] if act else "unknown")
        by_type[src_type] = by_type.get(src_type, 0.0) + e.co2e_kg
        by_capture[act.data_origin if act else "unknown"] = \
            by_capture.get(act.data_origin if act else "unknown", 0.0) + e.co2e_kg
    return {
        "scope": "scope_1",
        "year": year,
        "total_tco2e": kg_to_t(sum(e.co2e_kg for e in ems)),
        "source_types": [
            {"source_type": k, "tco2e": kg_to_t(v)}
            for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])
        ],
        "capture_methods": [
            {"data_origin": k, "tco2e": kg_to_t(v)}
            for k, v in sorted(by_capture.items(), key=lambda kv: -kv[1])
        ],
        "expected_source_types": [s.value for s in Scope1Source],
        "record_count": len(ems),
    }


@router.get("/scope2/summary")
def scope2_summary(year: int | None = None, entity_id: int | None = None,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal),
                   ctx: ScenarioContext = Depends(get_scenario_context)):
    """FR-3.A.2 - location-based AND market-based side by side."""
    stmt = _emission_query(p, ctx, scope=Scope.SCOPE_2, year=year, entity_id=entity_id)
    ems = list(db.scalars(stmt))
    location = sum(e.co2e_kg for e in ems if e.scope2_method != Scope2Method.MARKET_BASED)
    market = sum(e.co2e_kg for e in ems if e.scope2_method == Scope2Method.MARKET_BASED)
    by_country: dict[str, float] = {}
    for e in ems:
        if e.scope2_method != Scope2Method.MARKET_BASED:
            by_country[e.country] = by_country.get(e.country, 0.0) + e.co2e_kg
    return {
        "scope": "scope_2",
        "year": year,
        "location_based_tco2e": kg_to_t(location),
        "market_based_tco2e": kg_to_t(market),
        "difference_tco2e": kg_to_t(location - market),
        "renewable_benefit_pct": round((location - market) / location * 100, 2) if location else 0.0,
        "by_country": [
            {"country": k, "tco2e": kg_to_t(v)}
            for k, v in sorted(by_country.items(), key=lambda kv: -kv[1])
        ],
        "record_count": len(ems),
    }


@router.get("/scope3/summary")
def scope3_summary(year: int | None = None, entity_id: int | None = None,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal),
                   ctx: ScenarioContext = Depends(get_scenario_context)):
    """FR-3.A.3 - all 15 categories, always listed even when empty."""
    stmt = _emission_query(p, ctx, scope=Scope.SCOPE_3, year=year, entity_id=entity_id)
    ems = list(db.scalars(stmt))
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.scope == Scope.SCOPE_3))}
    totals: dict[int, float] = {}
    counts: dict[int, int] = {}
    methods: dict[int, set] = {}
    for e in ems:
        cat = cats.get(e.category_id)
        num = cat.number if cat else 0
        totals[num] = totals.get(num, 0.0) + e.co2e_kg
        counts[num] = counts.get(num, 0) + 1
        act_id = db.get(Calculation, e.calculation_id).activity_data_id
        act = db.get(ActivityData, act_id)
        methods.setdefault(num, set()).add(act.scope3_method or "unspecified")

    total = sum(totals.values())
    categories = []
    for num, name in SCOPE3_CATEGORIES.items():
        kg = totals.get(num, 0.0)
        categories.append({
            "number": num, "name": name,
            "tco2e": kg_to_t(kg),
            "share_pct": round(kg / total * 100, 2) if total else 0.0,
            "record_count": counts.get(num, 0),
            "methods_used": sorted(methods.get(num, set())),
            "is_reported": counts.get(num, 0) > 0,
        })
    return {
        "scope": "scope_3",
        "year": year,
        "total_tco2e": kg_to_t(total),
        "categories": categories,
        "categories_reported": sum(1 for c in categories if c["is_reported"]),
        "categories_total": 15,
        "coverage_pct": round(sum(1 for c in categories if c["is_reported"]) / 15 * 100, 1),
        "data_methods": SCOPE3_DATA_METHODS,
    }


@router.get("/emissions")
def list_emissions(
    scope: str | None = None, entity_id: int | None = None, facility_id: int | None = None,
    supplier_id: int | None = None, product_id: int | None = None, year: int | None = None,
    page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    stmt = select(Emission).order_by(Emission.co2e_kg.desc())
    for col, val in (("scope", scope), ("entity_id", entity_id), ("facility_id", facility_id),
                     ("supplier_id", supplier_id), ("product_id", product_id), ("year", year)):
        if val is not None:
            stmt = stmt.where(getattr(Emission, col) == val)
    stmt = ctx.filter(scoped(stmt, Emission, p), Emission)
    return page_response(db, stmt, page=page, page_size=page_size,
                         mapper=lambda e: to_dict(e, extra={"co2e_tonnes": kg_to_t(e.co2e_kg)}))


@router.get("/emissions/{emission_id}/lineage")
def emission_lineage(emission_id: int, db: Session = Depends(get_db),
                     p: Principal = Depends(get_principal)):
    """FR-7.2 - click any reported number, get its whole origin."""
    try:
        return lineage.trace_reported_value(db, emission_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
