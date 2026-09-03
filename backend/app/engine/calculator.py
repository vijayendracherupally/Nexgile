"""The calculation engine (FR-3.A.4).

One deterministic, reproducible pipeline:

    normalize -> resolve factor -> apply factor -> GWP -> allocate ->
    consolidate -> quantify uncertainty -> persist with full lineage

Re-running never mutates an existing result. It produces a new version and an
impact analysis (see recalc.py), which is what FR-7.3 means by
"recalculation impact analysis, review/approval, restatement, and reproducibility".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import CalculationStatus, ConsolidationMethod, Scope
from app.domain.models import (
    ActivityData, Allocation, Calculation, Emission, EmissionFactor, Entity,
    Facility, ReportingBoundary,
)
from app.engine import allocation as alloc_mod
from app.engine import consolidation, factors, gwp, lineage, uncertainty, units


class CalculationError(ValueError):
    pass


class LockedPeriodError(PermissionError):
    """FR-7.3 - approved/locked values are immutable."""


@dataclass
class CalculationOptions:
    gwp_set: str = settings.default_gwp_set
    method_version: str = settings.default_method_version
    library_id: int | None = None
    allocation_targets: list[alloc_mod.AllocationTarget] = field(default_factory=list)
    allocation_basis: str = "mass"
    consolidation_method: str | None = None
    scenario_id: int | None = None
    assumptions: list[str] = field(default_factory=list)
    force_method: str | None = None


@dataclass
class CalculationResult:
    calculation: Calculation
    emission: Emission
    allocations: list[Allocation]
    warnings: list[str]


def _facility_country(db: Session, activity: ActivityData) -> str:
    if activity.facility_id:
        fac = db.get(Facility, activity.facility_id)
        if fac and fac.country:
            return fac.country
    ent = db.get(Entity, activity.entity_id)
    return ent.country if ent and ent.country else "GLOBAL"


def _resolve_method(activity: ActivityData, options: CalculationOptions) -> str:
    if options.force_method:
        return options.force_method
    if activity.scope == Scope.SCOPE_2:
        return activity.scope2_method or "location_based"
    if activity.scope == Scope.SCOPE_3:
        return activity.scope3_method or "spend_based"
    return activity.data_origin or "activity_based"


def _consolidation_method(db: Session, activity: ActivityData,
                          options: CalculationOptions) -> str:
    if options.consolidation_method:
        return options.consolidation_method
    ent = db.get(Entity, activity.entity_id)
    if ent:
        boundary = db.scalars(
            select(ReportingBoundary)
            .where(ReportingBoundary.organization_id == ent.organization_id)
        ).first()
        if boundary:
            return boundary.consolidation_method
        return ent.consolidation_method
    return ConsolidationMethod.OPERATIONAL_CONTROL


def calculate(db: Session, activity: ActivityData,
              options: CalculationOptions | None = None) -> CalculationResult:
    """Run the pipeline for a single ActivityData row."""
    options = options or CalculationOptions()
    warnings: list[str] = []
    assumptions: list[str] = list(options.assumptions)

    # FR-7.8: a scenario calculation must carry the scenario of its input, and
    # an actual calculation may never be produced from scenario input.
    scenario_id = options.scenario_id if options.scenario_id is not None else activity.scenario_id
    if activity.scenario_id is not None and scenario_id != activity.scenario_id:
        raise CalculationError(
            "Scenario isolation violation: cannot calculate actuals from scenario activity data"
        )

    # --- 2. resolve the factor -------------------------------------------------
    library_id = options.library_id
    if library_id is None:
        library_id = factors.default_library(db).id
    country = _facility_country(db, activity)
    method = _resolve_method(activity, options)
    period = activity.period_start

    match = factors.resolve(
        db, activity_key=activity.activity_key, country=country, period=period,
        method=method if activity.scope == Scope.SCOPE_2 else None,
        library_id=library_id, scope=activity.scope,
    )
    factor = match.factor
    library = factor.library
    if factor.country in ("GLOBAL", ""):
        assumptions.append(
            f"No country-specific factor for {country}; global average factor applied."
        )
        warnings.append(f"Global fallback factor used for {country}")

    # --- 1. normalize the quantity to the factor's denominator -----------------
    conv = units.normalize(
        activity.quantity, activity.unit, factor.unit,
        substance=activity.activity_key.split(".")[-1],
    )
    normalized_qty = conv.quantity

    # --- 3. apply the factor, then GWP ----------------------------------------
    if factor.gas_breakdown:
        gas_masses = {g: normalized_qty * v for g, v in factor.gas_breakdown.items()}
        co2e_kg, gas_detail = gwp.to_co2e(gas_masses, options.gwp_set)
        factor_value_used = factor.value_kgco2e
    else:
        co2e_kg = normalized_qty * factor.value_kgco2e
        gas_masses = {"CO2e": co2e_kg}
        gas_detail = {"CO2e": {"mass_kg": co2e_kg, "gwp": 1.0, "co2e_kg": co2e_kg}}
        factor_value_used = factor.value_kgco2e
        assumptions.append(
            "Factor supplied as pre-aggregated CO2e; no per-gas breakdown available."
        )

    # --- 4. allocation ---------------------------------------------------------
    allocation_detail = None
    allocation_share = 1.0
    allocated_rows: list[Allocation] = []
    if options.allocation_targets:
        shares = alloc_mod.allocate(co2e_kg, options.allocation_targets, options.allocation_basis)
        allocation_detail = {
            "applied": True,
            "basis": options.allocation_basis,
            "splits": [
                {"target_type": s.target_type, "target_id": s.target_id,
                 "label": s.label, "basis_value": s.basis_value,
                 "share": round(s.share, 6),
                 "allocated_co2e_kg": round(s.allocated_co2e_kg, 6)}
                for s in shares
            ],
        }
        allocation_share = shares[0].share if shares else 1.0

    # --- 5. consolidation ------------------------------------------------------
    cons_method = _consolidation_method(db, activity, options)
    own = consolidation.ownership_share(db, activity.entity_id, cons_method)
    consolidated = co2e_kg * own.share
    if own.share == 0.0:
        warnings.append(
            f"Entity excluded from the group boundary under {cons_method}; "
            "consolidated amount is zero."
        )

    # --- 6. uncertainty & confidence ------------------------------------------
    year_gap = abs(period.year - factor.valid_from.year)
    unc = uncertainty.assess(
        data_origin=activity.data_origin,
        factor_uncertainty_pct=factor.uncertainty_pct,
        completeness_pct=activity.completeness_pct,
        factor_country_matches=(factor.country == country),
        factor_year_gap=year_gap,
        factor_technology_match=True,
        evidence_present=activity.evidence_status in ("validated", "accepted"),
    )

    # --- 7. persist with lineage ----------------------------------------------
    formula = (
        f"{activity.quantity:g} {activity.unit}"
        + (f" -> {normalized_qty:.6g} {factor.unit}" if activity.unit != factor.unit else "")
        + f" x {factor_value_used:g} kgCO2e/{factor.unit}"
        + (f" [{options.gwp_set} GWP applied per gas]" if factor.gas_breakdown else "")
        + f" = {co2e_kg:.4f} kgCO2e"
        + (f" x allocation {allocation_share:.4f}" if allocation_detail else "")
        + f" x ownership {own.share:.4f} ({cons_method})"
        + f" = {consolidated:.4f} kgCO2e consolidated"
    )

    trace = lineage.build(
        activity=activity, factor=factor, library=library,
        method=method, method_version=options.method_version, gwp_set=options.gwp_set,
        conversion_chain=conv.chain, gas_detail=gas_detail,
        allocation_detail=allocation_detail,
        consolidation_detail={
            "method": cons_method, "share": own.share,
            "explanation": own.explanation, "ownership_path": own.path,
        },
        uncertainty_detail={
            "uncertainty_pct": unc.uncertainty_pct,
            "confidence_score": unc.confidence_score,
            "rating": unc.rating,
            "pedigree": unc.pedigree,
            "components": unc.components,
            "factor_selection_score": match.score,
            "factor_selection_reasons": match.reasons,
        },
        factor_alternatives=factors.alternatives(
            db, activity_key=activity.activity_key, country=country,
            period=period, method=method, library_id=library_id,
        ),
        assumptions=assumptions,
    )

    calc = Calculation(
        activity_data_id=activity.id,
        emission_factor_id=factor.id,
        factor_library_id=library.id,
        factor_library_version=library.version,
        method=method,
        method_version=options.method_version,
        gwp_set=options.gwp_set,
        input_quantity=activity.quantity,
        input_unit=activity.unit,
        normalized_quantity=normalized_qty,
        normalized_unit=factor.unit,
        unit_conversion_chain=conv.chain,
        factor_value=factor_value_used,
        gas_results_kg={k: round(v, 6) for k, v in gas_masses.items()},
        co2e_kg=co2e_kg,
        allocation_basis=options.allocation_basis if allocation_detail else None,
        allocation_share=allocation_share,
        consolidation_method=cons_method,
        ownership_share=own.share,
        consolidated_co2e_kg=consolidated,
        uncertainty_pct=unc.uncertainty_pct,
        confidence_score=unc.confidence_score,
        data_quality_rating=unc.rating,
        status=CalculationStatus.CALCULATED,
        version=1,
        formula=formula,
        assumptions=assumptions,
        lineage=trace,
        scenario_id=scenario_id,
    )
    db.add(calc)
    db.flush()

    if allocation_detail:
        for s in alloc_mod.allocate(co2e_kg, options.allocation_targets, options.allocation_basis):
            row = Allocation(
                calculation_id=calc.id, target_type=s.target_type, target_id=s.target_id,
                basis=s.basis, basis_value=s.basis_value, share=s.share,
                allocated_co2e_kg=s.allocated_co2e_kg,
            )
            db.add(row)
            allocated_rows.append(row)

    emission = Emission(
        calculation_id=calc.id,
        entity_id=activity.entity_id,
        facility_id=activity.facility_id,
        cost_center_id=activity.cost_center_id,
        supplier_id=activity.supplier_id,
        product_id=activity.product_id,
        category_id=activity.category_id,
        scope=activity.scope,
        scope2_method=activity.scope2_method,
        country=country,
        period_start=activity.period_start,
        period_end=activity.period_end,
        year=activity.period_start.year,
        co2e_kg=consolidated,
        data_quality_rating=unc.rating,
        confidence_score=unc.confidence_score,
        is_estimated=activity.is_estimated,
        status=CalculationStatus.CALCULATED,
        scenario_id=scenario_id,
    )
    db.add(emission)
    db.flush()

    lineage.record_change(
        db, action="calculate", object_type="calculation", object_id=calc.id,
        after={"co2e_kg": co2e_kg, "consolidated_co2e_kg": consolidated,
               "factor_id": factor.id, "library_version": library.version},
        reason="Initial calculation",
    )
    return CalculationResult(calc, emission, allocated_rows, warnings)


def calculate_batch(db: Session, activities: list[ActivityData],
                    options: CalculationOptions | None = None) -> dict:
    """FR-7.7 - calculation batches."""
    ok, failed = 0, 0
    errors: list[dict] = []
    warnings: list[str] = []
    total = 0.0
    for a in activities:
        try:
            res = calculate(db, a, options)
            total += res.emission.co2e_kg
            warnings.extend(res.warnings)
            ok += 1
        except Exception as exc:  # a bad row must not abort the batch
            failed += 1
            errors.append({"activity_data_id": a.id, "error": str(exc),
                           "activity_key": a.activity_key})
    return {
        "calculated": ok, "failed": failed,
        "total_co2e_kg": round(total, 3),
        "total_co2e_tonnes": round(total / 1000, 3),
        "errors": errors[:200],
        "warnings": sorted(set(warnings))[:100],
    }


def approve(db: Session, calc: Calculation, *, user_id: int | None,
            user_email: str = "", comment: str = "") -> Calculation:
    """FR-7.3 - approval freezes the value."""
    if calc.status in (CalculationStatus.LOCKED,):
        raise LockedPeriodError("Calculation is locked and cannot be re-approved")
    before = {"status": calc.status}
    calc.status = CalculationStatus.APPROVED
    calc.approved_by_id = user_id
    calc.approved_at = datetime.now(timezone.utc)
    em = db.scalars(select(Emission).where(Emission.calculation_id == calc.id)).first()
    if em:
        em.status = CalculationStatus.APPROVED
    lineage.record_change(db, action="approve", object_type="calculation",
                          object_id=calc.id, user_id=user_id, user_email=user_email,
                          before=before, after={"status": calc.status}, reason=comment)
    return calc


def lock(db: Session, calc: Calculation, *, user_id: int | None,
         user_email: str = "", reason: str = "Period close") -> Calculation:
    if calc.status != CalculationStatus.APPROVED:
        raise LockedPeriodError("Only approved calculations can be locked")
    before = {"status": calc.status}
    calc.status = CalculationStatus.LOCKED
    calc.locked_at = datetime.now(timezone.utc)
    em = db.scalars(select(Emission).where(Emission.calculation_id == calc.id)).first()
    if em:
        em.status = CalculationStatus.LOCKED
    lineage.record_change(db, action="lock", object_type="calculation", object_id=calc.id,
                          user_id=user_id, user_email=user_email, before=before,
                          after={"status": calc.status}, reason=reason)
    return calc


def reproduce(db: Session, calc: Calculation) -> dict:
    """FR-7.3 reproducibility: recompute from the stored lineage alone and
    confirm the number comes out identical."""
    activity = db.get(ActivityData, calc.activity_data_id)
    if activity is None:
        return {"reproducible": False, "reason": "source activity data deleted"}
    factor = db.get(EmissionFactor, calc.emission_factor_id)
    if factor is None:
        return {"reproducible": False, "reason": "emission factor no longer available"}

    conv = units.normalize(calc.input_quantity, calc.input_unit, calc.normalized_unit,
                           substance=activity.activity_key.split(".")[-1])
    if factor.gas_breakdown:
        gas_masses = {g: conv.quantity * v for g, v in factor.gas_breakdown.items()}
        recomputed, _ = gwp.to_co2e(gas_masses, calc.gwp_set)
    else:
        recomputed = conv.quantity * calc.factor_value

    delta = recomputed - calc.co2e_kg
    return {
        "reproducible": abs(delta) < max(1e-6, abs(calc.co2e_kg) * 1e-9),
        "stored_co2e_kg": calc.co2e_kg,
        "recomputed_co2e_kg": round(recomputed, 6),
        "delta_kg": round(delta, 9),
        "method_version": calc.method_version,
        "factor_library_version": calc.factor_library_version,
        "gwp_set": calc.gwp_set,
    }
