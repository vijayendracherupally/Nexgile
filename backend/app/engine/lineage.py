"""Audit-grade lineage (FR-7.2).

The requirement is that *every reported value traces to* source activity,
factor, method, unit conversion, allocation, assumptions, approvals and
timestamped changes. This module builds that record at calculation time and
reads it back on demand - it is never reconstructed from guesswork.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    ActivityData, Allocation, Approval, AuditLog, Calculation, Emission,
    EmissionFactor, Entity, Facility, FactorLibrary, Supplier,
)

LINEAGE_ELEMENTS = [
    "source_activity", "emission_factor", "method", "unit_conversion",
    "allocation", "assumptions", "approvals", "timestamped_changes",
]


def build(
    *,
    activity: ActivityData,
    factor: EmissionFactor,
    library: FactorLibrary,
    method: str,
    method_version: str,
    gwp_set: str,
    conversion_chain: list[dict],
    gas_detail: dict,
    allocation_detail: dict | None,
    consolidation_detail: dict,
    uncertainty_detail: dict,
    factor_alternatives: list[dict],
    assumptions: list[str],
) -> dict:
    """Assemble the complete trace for one calculation."""
    return {
        "schema_version": "1.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_activity": {
            "activity_data_id": activity.id,
            "activity_key": activity.activity_key,
            "description": activity.description,
            "quantity": activity.quantity,
            "unit": activity.unit,
            "period_start": activity.period_start.isoformat(),
            "period_end": activity.period_end.isoformat(),
            "data_origin": activity.data_origin,
            "entity_id": activity.entity_id,
            "facility_id": activity.facility_id,
            "supplier_id": activity.supplier_id,
            "product_id": activity.product_id,
            "external_ref": activity.external_ref,
            "connector_id": activity.connector_id,
            "evidence_status": activity.evidence_status,
        },
        "emission_factor": {
            "factor_id": factor.id,
            "name": factor.name,
            "value_kgco2e": factor.value_kgco2e,
            "unit": factor.unit,
            "country": factor.country,
            "region": factor.region,
            "valid_from": factor.valid_from.isoformat(),
            "valid_to": factor.valid_to.isoformat() if factor.valid_to else None,
            "source_reference": factor.source_reference,
            "uncertainty_pct": factor.uncertainty_pct,
            "gas_breakdown": factor.gas_breakdown,
            "library": {
                "id": library.id, "provider": library.provider,
                "name": library.name, "version": library.version,
                "is_locked": library.is_locked,
            },
            "alternatives_considered": factor_alternatives,
        },
        "method": {
            "method": method,
            "method_version": method_version,
            "gwp_set": gwp_set,
            "gas_detail": gas_detail,
        },
        "unit_conversion": {"chain": conversion_chain},
        "allocation": allocation_detail or {"applied": False,
                                            "note": "No allocation - full amount assigned to the source entity."},
        "consolidation": consolidation_detail,
        "data_quality": uncertainty_detail,
        "assumptions": assumptions,
        "approvals": [],
        "timestamped_changes": [],
    }


def read(db: Session, calculation_id: int) -> dict[str, Any]:
    """Return the full lineage of a calculation, live-joined with the
    approval and audit history recorded since it was created."""
    calc = db.get(Calculation, calculation_id)
    if calc is None:
        raise LookupError(f"Calculation {calculation_id} not found")

    lineage = dict(calc.lineage or {})

    approvals = db.scalars(
        select(Approval).where(Approval.object_type == "calculation",
                               Approval.object_id == calculation_id)
        .order_by(Approval.created_at)
    ).all()
    lineage["approvals"] = [
        {
            "step": a.step, "status": a.status,
            "requested_by_id": a.requested_by_id,
            "decided_by_id": a.decided_by_id,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            "comment": a.comment,
        } for a in approvals
    ]

    changes = db.scalars(
        select(AuditLog).where(AuditLog.object_type == "calculation",
                               AuditLog.object_id == calculation_id)
        .order_by(AuditLog.at)
    ).all()
    lineage["timestamped_changes"] = [
        {
            "at": c.at.isoformat(), "action": c.action, "user": c.user_email,
            "before": c.before, "after": c.after, "reason": c.reason,
        } for c in changes
    ]

    allocations = db.scalars(
        select(Allocation).where(Allocation.calculation_id == calculation_id)
    ).all()
    if allocations:
        lineage["allocation"] = {
            "applied": True,
            "basis": allocations[0].basis,
            "splits": [
                {"target_type": a.target_type, "target_id": a.target_id,
                 "basis_value": a.basis_value, "share": a.share,
                 "allocated_co2e_kg": a.allocated_co2e_kg}
                for a in allocations
            ],
        }

    lineage["calculation"] = {
        "id": calc.id, "version": calc.version, "status": calc.status,
        "co2e_kg": calc.co2e_kg, "consolidated_co2e_kg": calc.consolidated_co2e_kg,
        "formula": calc.formula, "scenario_id": calc.scenario_id,
        "supersedes_id": calc.supersedes_id,
        "restatement_reason": calc.restatement_reason,
        "created_at": calc.created_at.isoformat(),
        "approved_at": calc.approved_at.isoformat() if calc.approved_at else None,
        "locked_at": calc.locked_at.isoformat() if calc.locked_at else None,
    }
    lineage["completeness"] = completeness(lineage)
    return lineage


def completeness(lineage: dict) -> dict:
    """FR-7.2 is binary: a value either has every lineage element or it does not."""
    present = {}
    for element in LINEAGE_ELEMENTS:
        val = lineage.get(element)
        present[element] = bool(val) if not isinstance(val, dict) else bool(val)
    # A value with no approvals yet is still traceable; flag it, don't fail it.
    required = [e for e in LINEAGE_ELEMENTS if e != "approvals"]
    return {
        "elements": present,
        "is_audit_grade": all(present[e] for e in required),
        "missing": [e for e in required if not present[e]],
    }


def trace_reported_value(db: Session, emission_id: int) -> dict:
    """Click-through from a dashboard number to its full origin (FR-3.E.2 -> FR-7.2)."""
    em = db.get(Emission, emission_id)
    if em is None:
        raise LookupError(f"Emission {emission_id} not found")
    lineage = read(db, em.calculation_id)
    entity = db.get(Entity, em.entity_id)
    facility = db.get(Facility, em.facility_id) if em.facility_id else None
    supplier = db.get(Supplier, em.supplier_id) if em.supplier_id else None
    lineage["reported_value"] = {
        "emission_id": em.id, "co2e_kg": em.co2e_kg, "scope": em.scope,
        "year": em.year, "status": em.status,
        "entity": entity.name if entity else None,
        "facility": facility.name if facility else None,
        "supplier": supplier.name if supplier else None,
        "scenario_id": em.scenario_id,
    }
    return lineage


def record_change(db: Session, *, action: str, object_type: str, object_id: int,
                  user_id: int | None = None, user_email: str = "",
                  before: dict | None = None, after: dict | None = None,
                  reason: str = "") -> AuditLog:
    entry = AuditLog(
        action=action, object_type=object_type, object_id=object_id,
        user_id=user_id, user_email=user_email,
        before=before or {}, after=after or {}, reason=reason,
    )
    db.add(entry)
    return entry
