"""The two structural guards of the platform.

1. `scoped()`  - FR-7.1 tenant/entity segregation, applied to every list query.
2. `ScenarioContext` / `guard_scenario_write()` - FR-7.8 scenario isolation:
   "forecasts and what-if models never alter approved actuals".

Both are enforced here rather than in endpoints, so that a forgetful endpoint
fails closed instead of leaking or corrupting.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import Select, false
from sqlalchemy.orm import Session

from app.core.rbac import Principal, get_principal
from app.domain.enums import CalculationStatus
from app.domain.models import (
    ActivityData, Calculation, Emission, Evidence, Facility, PCF, Product,
    ReductionInitiative, Report, Scenario, Submission, Supplier,
)

# Which column of a model carries the scoping key.
SCOPE_COLUMNS = {
    "entity_id": "entity_ids",
    "facility_id": "facility_ids",
    "supplier_id": "supplier_ids",
    "product_id": "product_ids",
    "organization_id": "organization_ids",
}


class ScenarioIsolationError(PermissionError):
    """Raised when a scenario context attempts to write approved actuals."""


def scoped(stmt: Select, model, principal: Principal) -> Select:
    """Narrow a SELECT to what the principal is permitted to see.

    Applies the most specific scoping column the model has. Unrestricted
    principals (platform administrators) pass through unchanged.
    """
    if principal.is_unrestricted:
        return stmt

    for column_name, attr in SCOPE_COLUMNS.items():
        column = getattr(model, column_name, None)
        if column is None:
            continue
        nullable = _is_nullable(column)
        permitted = getattr(principal, attr)
        if not permitted:
            # No grant for this dimension: fail closed.
            return stmt.where(column.is_(None)) if nullable else stmt.where(false())
        if nullable:
            stmt = stmt.where(column.in_(permitted) | column.is_(None))
        else:
            stmt = stmt.where(column.in_(permitted))
        return stmt

    return stmt


def _is_nullable(column) -> bool:
    try:
        return bool(column.property.columns[0].nullable)
    except Exception:
        return True


def scope_supplier_self(stmt: Select, model, principal: Principal) -> Select:
    """External supplier users see only their own rows (FR-2.3, FR-7.1)."""
    if principal.user.supplier_id and hasattr(model, "supplier_id"):
        stmt = stmt.where(model.supplier_id == principal.user.supplier_id)
    return stmt


# ---------------------------------------------------------------------------
# FR-7.8  Scenario isolation
# ---------------------------------------------------------------------------

# Every model that carries a scenario_id. Writing to any of these while a
# scenario is active must target that scenario, never NULL.
SCENARIO_MODELS = (ActivityData, Calculation, Emission, PCF, ReductionInitiative)

IMMUTABLE_STATUSES = {CalculationStatus.APPROVED, CalculationStatus.LOCKED}


@dataclass
class ScenarioContext:
    """The address space a request writes into.

    scenario_id is None  -> approved actuals
    scenario_id is set   -> a sandbox that can never touch actuals
    """
    scenario_id: int | None = None

    @property
    def is_sandbox(self) -> bool:
        return self.scenario_id is not None

    def stamp(self, obj) -> None:
        """Apply the context to a new object before it is added to the session."""
        if hasattr(obj, "scenario_id"):
            obj.scenario_id = self.scenario_id

    def filter(self, stmt: Select, model) -> Select:
        col = getattr(model, "scenario_id", None)
        if col is None:
            return stmt
        return stmt.where(col.is_(None) if self.scenario_id is None
                          else col == self.scenario_id)


def get_scenario_context(
    scenario_id: int | None = Query(
        default=None,
        description="Run in a scenario sandbox. Omit for approved actuals (FR-7.8).",
    ),
    principal: Principal = Depends(get_principal),
) -> ScenarioContext:
    return ScenarioContext(scenario_id=scenario_id)


def guard_scenario_write(ctx: ScenarioContext, obj) -> None:
    """The structural guarantee.

    A write made inside a scenario context may not land on an actual row, and
    a write made outside a scenario may not modify an approved or locked value.
    """
    obj_scenario = getattr(obj, "scenario_id", None)

    if ctx.is_sandbox:
        if obj_scenario is None:
            raise ScenarioIsolationError(
                "Scenario isolation (FR-7.8): a what-if or forecast may not write to "
                "approved actuals. The object must carry scenario_id="
                f"{ctx.scenario_id}."
            )
        if obj_scenario != ctx.scenario_id:
            raise ScenarioIsolationError(
                f"Scenario isolation (FR-7.8): object belongs to scenario "
                f"{obj_scenario}, but the request runs in scenario {ctx.scenario_id}."
            )
        return

    status_value = getattr(obj, "status", None)
    if status_value in IMMUTABLE_STATUSES:
        raise ScenarioIsolationError(
            f"Calculation governance (FR-7.3): this value is {status_value} and is "
            "immutable. Restate it instead of editing it."
        )


def require_scenario(db: Session, ctx: ScenarioContext) -> Scenario | None:
    if ctx.scenario_id is None:
        return None
    scenario = db.get(Scenario, ctx.scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"Scenario {ctx.scenario_id} not found")
    if scenario.is_locked:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Scenario '{scenario.name}' is locked")
    return scenario


def assert_visible(principal: Principal, *, object_type: str, object_id: int | None) -> None:
    """Point lookups go through the same rule as list queries."""
    if principal.is_unrestricted or object_id is None:
        return
    mapping = {
        "entity": principal.entity_ids,
        "facility": principal.facility_ids,
        "supplier": principal.supplier_ids,
        "product": principal.product_ids,
        "organization": principal.organization_ids,
    }
    permitted = mapping.get(object_type)
    if permitted is not None and object_id not in permitted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"Not permitted to access {object_type} {object_id} (FR-7.1)",
        )
