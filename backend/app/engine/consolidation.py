"""Consolidation up the organization tree (FR-3.A.5).

The reporting boundary's consolidation method decides how much of a
subsidiary's emissions the group reports.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ConsolidationMethod
from app.domain.models import Entity


@dataclass
class OwnershipResult:
    share: float
    method: str
    explanation: str
    path: list[dict]


def ownership_share(db: Session, entity_id: int,
                    method: str = ConsolidationMethod.OPERATIONAL_CONTROL) -> OwnershipResult:
    """Walk the entity tree to the top, applying the consolidation rule.

    - equity_share:       multiply ownership percentages up the chain
    - financial_control:  100% if control (>50%) all the way up, else 0%
    - operational_control:100% if the entity is flagged consolidated, else 0%
    """
    path: list[dict] = []
    entity = db.get(Entity, entity_id)
    if entity is None:
        return OwnershipResult(0.0, method, "Entity not found", path)

    if method == ConsolidationMethod.OPERATIONAL_CONTROL:
        share = 1.0 if entity.is_consolidated else 0.0
        path.append({"entity_id": entity.id, "name": entity.name,
                     "is_consolidated": entity.is_consolidated})
        return OwnershipResult(
            share, method,
            "Operational control: 100% of emissions from entities under the group's "
            "operational control, 0% otherwise.",
            path,
        )

    share = 1.0
    cursor: Entity | None = entity
    guard = 0
    while cursor is not None and guard < 50:
        guard += 1
        pct = (cursor.ownership_pct or 0.0) / 100.0
        path.append({"entity_id": cursor.id, "name": cursor.name,
                     "ownership_pct": cursor.ownership_pct})
        if method == ConsolidationMethod.EQUITY_SHARE:
            share *= pct
        else:  # financial control
            if pct <= 0.5:
                share = 0.0
                break
        cursor = db.get(Entity, cursor.parent_id) if cursor.parent_id else None

    if method == ConsolidationMethod.FINANCIAL_CONTROL and share > 0:
        share = 1.0

    explanation = (
        "Equity share: ownership percentages multiplied along the ownership chain."
        if method == ConsolidationMethod.EQUITY_SHARE else
        "Financial control: 100% where the group holds >50% along the whole chain, else 0%."
    )
    return OwnershipResult(share, method, explanation, path)


def descendant_entity_ids(db: Session, root_entity_id: int) -> list[int]:
    """All entities under a root, inclusive - the drill-down spine (FR-3.E.2)."""
    ids = [root_entity_id]
    frontier = [root_entity_id]
    guard = 0
    while frontier and guard < 100:
        guard += 1
        children = list(db.scalars(select(Entity.id).where(Entity.parent_id.in_(frontier))))
        children = [c for c in children if c not in ids]
        ids.extend(children)
        frontier = children
    return ids
