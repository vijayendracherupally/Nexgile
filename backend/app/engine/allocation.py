"""Allocation (FR-3.A.4 for organizational splits, FR-3.B.3 for LCA)."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import AllocationBasis


@dataclass
class AllocationTarget:
    target_type: str
    target_id: int
    basis_value: float
    label: str = ""


@dataclass
class AllocatedShare:
    target_type: str
    target_id: int
    label: str
    basis: str
    basis_value: float
    share: float
    allocated_co2e_kg: float


class AllocationError(ValueError):
    pass


def allocate(
    total_co2e_kg: float,
    targets: list[AllocationTarget],
    basis: str = AllocationBasis.MASS,
) -> list[AllocatedShare]:
    """Split a total across targets in proportion to the chosen basis.

    Shares always sum to exactly 1.0 (the residual lands on the last target)
    so that consolidation can never lose or invent grams.
    """
    if not targets:
        raise AllocationError("No allocation targets supplied")
    denominator = sum(t.basis_value for t in targets)
    if denominator <= 0:
        # Equal split is the documented fallback; it is recorded as an assumption.
        share = 1.0 / len(targets)
        return [
            AllocatedShare(t.target_type, t.target_id, t.label, f"{basis}:equal_fallback",
                           t.basis_value, share, total_co2e_kg * share)
            for t in targets
        ]

    shares: list[AllocatedShare] = []
    running = 0.0
    for i, t in enumerate(targets):
        if i == len(targets) - 1:
            share = 1.0 - running
        else:
            share = t.basis_value / denominator
            running += share
        shares.append(AllocatedShare(
            t.target_type, t.target_id, t.label, basis, t.basis_value,
            share, total_co2e_kg * share,
        ))
    return shares


def economic_allocation(total_co2e_kg: float, revenues: dict[int, float],
                        target_type: str = "product") -> list[AllocatedShare]:
    targets = [AllocationTarget(target_type, k, v) for k, v in revenues.items()]
    return allocate(total_co2e_kg, targets, AllocationBasis.ECONOMIC)


def mass_allocation(total_co2e_kg: float, masses: dict[int, float],
                    target_type: str = "product") -> list[AllocatedShare]:
    targets = [AllocationTarget(target_type, k, v) for k, v in masses.items()]
    return allocate(total_co2e_kg, targets, AllocationBasis.MASS)


def available_bases() -> list[str]:
    return [b.value for b in AllocationBasis]
