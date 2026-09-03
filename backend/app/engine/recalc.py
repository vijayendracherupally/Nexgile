"""Recalculation, impact analysis and restatement (FR-7.3).

A factor library update, a methodology change or a GWP-set change must never
silently rewrite history. It produces:
  1. an *impact analysis*  - what would change, by how much, where
  2. on acceptance, a *restatement* - new calculation versions, the old ones
     marked superseded, with a reason and a full audit entry
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import CalculationStatus
from app.domain.models import (
    ActivityData, Baseline, Calculation, Emission, Entity, FactorLibrary,
)
from app.engine import lineage
from app.engine.calculator import CalculationOptions, calculate


@dataclass
class ImpactLine:
    calculation_id: int
    entity_id: int
    scope: str
    year: int
    old_co2e_kg: float
    new_co2e_kg: float
    delta_kg: float
    delta_pct: float
    driver: str


def impact_analysis(
    db: Session,
    *,
    calculation_ids: list[int] | None = None,
    new_library_id: int | None = None,
    new_gwp_set: str | None = None,
    new_method_version: str | None = None,
    entity_id: int | None = None,
    year: int | None = None,
) -> dict:
    """Dry-run: compute what the change would do, changing nothing.

    Runs inside a nested transaction that is always rolled back, so the
    analysis is exact rather than approximate - it uses the real engine.
    """
    stmt = select(Calculation).where(Calculation.scenario_id.is_(None))
    if calculation_ids:
        stmt = stmt.where(Calculation.id.in_(calculation_ids))
    stmt = stmt.where(Calculation.status.in_([
        CalculationStatus.CALCULATED, CalculationStatus.APPROVED, CalculationStatus.LOCKED,
    ]))
    calcs = list(db.scalars(stmt))

    if entity_id or year:
        filtered = []
        for c in calcs:
            act = db.get(ActivityData, c.activity_data_id)
            if act is None:
                continue
            if entity_id and act.entity_id != entity_id:
                continue
            if year and act.period_start.year != year:
                continue
            filtered.append(c)
        calcs = filtered

    driver_parts = []
    if new_library_id:
        lib = db.get(FactorLibrary, new_library_id)
        driver_parts.append(f"factor library -> {lib.provider} {lib.version}" if lib else "factor library")
    if new_gwp_set:
        driver_parts.append(f"GWP set -> {new_gwp_set}")
    if new_method_version:
        driver_parts.append(f"method -> {new_method_version}")
    driver = "; ".join(driver_parts) or "re-run with current configuration"

    lines: list[ImpactLine] = []
    errors: list[dict] = []

    savepoint = db.begin_nested()
    try:
        for c in calcs:
            act = db.get(ActivityData, c.activity_data_id)
            if act is None:
                continue
            opts = CalculationOptions(
                gwp_set=new_gwp_set or c.gwp_set,
                method_version=new_method_version or c.method_version,
                library_id=new_library_id or c.factor_library_id,
                consolidation_method=c.consolidation_method,
            )
            try:
                res = calculate(db, act, opts)
            except Exception as exc:
                errors.append({"calculation_id": c.id, "error": str(exc)})
                continue
            new_val = res.emission.co2e_kg
            old_val = c.consolidated_co2e_kg
            delta = new_val - old_val
            lines.append(ImpactLine(
                calculation_id=c.id, entity_id=act.entity_id, scope=act.scope,
                year=act.period_start.year, old_co2e_kg=old_val, new_co2e_kg=new_val,
                delta_kg=delta,
                delta_pct=(delta / old_val * 100) if old_val else 0.0,
                driver=driver,
            ))
    finally:
        savepoint.rollback()

    total_old = sum(l.old_co2e_kg for l in lines)
    total_new = sum(l.new_co2e_kg for l in lines)
    by_entity: dict[int, dict] = {}
    by_scope: dict[str, dict] = {}
    for l in lines:
        e = by_entity.setdefault(l.entity_id, {"entity_id": l.entity_id, "old": 0.0, "new": 0.0})
        e["old"] += l.old_co2e_kg
        e["new"] += l.new_co2e_kg
        s = by_scope.setdefault(l.scope, {"scope": l.scope, "old": 0.0, "new": 0.0})
        s["old"] += l.old_co2e_kg
        s["new"] += l.new_co2e_kg

    for group in (by_entity, by_scope):
        for v in group.values():
            v["delta"] = round(v["new"] - v["old"], 3)
            v["delta_pct"] = round((v["new"] - v["old"]) / v["old"] * 100, 3) if v["old"] else 0.0
            v["old"] = round(v["old"], 3)
            v["new"] = round(v["new"], 3)

    for e in by_entity.values():
        ent = db.get(Entity, e["entity_id"])
        e["entity_name"] = ent.name if ent else str(e["entity_id"])

    material = [l for l in lines if abs(l.delta_pct) >= 5.0]
    return {
        "driver": driver,
        "calculations_examined": len(calcs),
        "calculations_impacted": len([l for l in lines if abs(l.delta_kg) > 1e-9]),
        "total_old_tco2e": round(total_old / 1000, 3),
        "total_new_tco2e": round(total_new / 1000, 3),
        "delta_tco2e": round((total_new - total_old) / 1000, 3),
        "delta_pct": round((total_new - total_old) / total_old * 100, 3) if total_old else 0.0,
        "materially_impacted_count": len(material),
        "restatement_recommended": abs(
            (total_new - total_old) / total_old * 100 if total_old else 0.0
        ) >= 5.0,
        "by_entity": sorted(by_entity.values(), key=lambda d: abs(d["delta"]), reverse=True),
        "by_scope": sorted(by_scope.values(), key=lambda d: d["scope"]),
        "top_changes": [
            {
                "calculation_id": l.calculation_id, "entity_id": l.entity_id,
                "scope": l.scope, "year": l.year,
                "old_co2e_kg": round(l.old_co2e_kg, 3),
                "new_co2e_kg": round(l.new_co2e_kg, 3),
                "delta_kg": round(l.delta_kg, 3),
                "delta_pct": round(l.delta_pct, 2),
            }
            for l in sorted(lines, key=lambda x: abs(x.delta_kg), reverse=True)[:50]
        ],
        "errors": errors[:50],
    }


def restate(
    db: Session,
    *,
    calculation_ids: list[int],
    reason: str,
    new_library_id: int | None = None,
    new_gwp_set: str | None = None,
    new_method_version: str | None = None,
    user_id: int | None = None,
    user_email: str = "",
    allow_locked: bool = False,
) -> dict:
    """Apply the change for real, creating new versions and superseding the old."""
    if not reason.strip():
        raise ValueError("A restatement requires a documented reason (FR-7.3)")

    restated, skipped = [], []
    for cid in calculation_ids:
        old = db.get(Calculation, cid)
        if old is None:
            skipped.append({"calculation_id": cid, "reason": "not found"})
            continue
        if old.status == CalculationStatus.LOCKED and not allow_locked:
            skipped.append({"calculation_id": cid,
                            "reason": "locked - unlock or set allow_locked to restate"})
            continue
        act = db.get(ActivityData, old.activity_data_id)
        if act is None:
            skipped.append({"calculation_id": cid, "reason": "source activity missing"})
            continue

        opts = CalculationOptions(
            gwp_set=new_gwp_set or old.gwp_set,
            method_version=new_method_version or old.method_version,
            library_id=new_library_id or old.factor_library_id,
            consolidation_method=old.consolidation_method,
            assumptions=[f"Restatement of calculation #{old.id}: {reason}"],
        )
        res = calculate(db, act, opts)
        new = res.calculation
        new.version = old.version + 1
        new.supersedes_id = old.id
        new.restatement_reason = reason
        new.status = CalculationStatus.RESTATED

        before = {"status": old.status, "co2e_kg": old.co2e_kg,
                  "consolidated_co2e_kg": old.consolidated_co2e_kg}
        old.status = CalculationStatus.SUPERSEDED
        old_em = db.scalars(select(Emission).where(Emission.calculation_id == old.id)).first()
        if old_em:
            old_em.status = CalculationStatus.SUPERSEDED

        lineage.record_change(
            db, action="restate", object_type="calculation", object_id=old.id,
            user_id=user_id, user_email=user_email, before=before,
            after={"status": old.status, "superseded_by": new.id,
                   "new_co2e_kg": new.co2e_kg}, reason=reason,
        )
        restated.append({
            "old_calculation_id": old.id, "new_calculation_id": new.id,
            "old_co2e_kg": round(before["consolidated_co2e_kg"], 3),
            "new_co2e_kg": round(new.consolidated_co2e_kg, 3),
            "delta_kg": round(new.consolidated_co2e_kg - before["consolidated_co2e_kg"], 3),
            "version": new.version,
        })

    db.flush()
    return {
        "restated_count": len(restated),
        "skipped_count": len(skipped),
        "reason": reason,
        "restated": restated,
        "skipped": skipped,
        "restated_at": datetime.now(timezone.utc).isoformat(),
    }


def recalculate_baseline(db: Session, *, entity_id: int, year: int,
                         reason: str, user_id: int | None = None) -> dict:
    """FR-3.A.5 / FR-7.3 - baseline recalculation after a structural change."""
    rows = db.scalars(
        select(Emission).where(
            Emission.entity_id == entity_id,
            Emission.year == year,
            Emission.scenario_id.is_(None),
        )
    ).all()
    by_scope: dict[str, float] = {}
    for r in rows:
        by_scope[r.scope] = by_scope.get(r.scope, 0.0) + r.co2e_kg

    updated = []
    for scope, kg in by_scope.items():
        tonnes = kg / 1000
        bl = db.scalars(
            select(Baseline).where(Baseline.entity_id == entity_id,
                                   Baseline.year == year, Baseline.scope == scope)
        ).first()
        if bl is None:
            bl = Baseline(entity_id=entity_id, year=year, scope=scope, co2e_tonnes=tonnes)
            db.add(bl)
            old = None
        else:
            if bl.locked:
                continue
            old = bl.co2e_tonnes
            bl.co2e_tonnes = tonnes
        bl.is_recalculated = True
        bl.recalculation_reason = reason
        updated.append({"scope": scope, "old_tco2e": old, "new_tco2e": round(tonnes, 3)})
        lineage.record_change(db, action="recalculate_baseline", object_type="baseline",
                              object_id=bl.id or 0, user_id=user_id,
                              before={"co2e_tonnes": old}, after={"co2e_tonnes": tonnes},
                              reason=reason)
    db.flush()
    return {"entity_id": entity_id, "year": year, "reason": reason, "baselines": updated}
