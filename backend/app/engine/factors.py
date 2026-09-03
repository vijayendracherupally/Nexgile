"""Emission-factor resolution (FR-3.A.4) under version locking (FR-7.3).

Selection is deterministic and explainable: candidates are scored on
specificity, and the winning score plus the runners-up are written into the
lineage so an auditor can see *why* this factor and not another.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import EmissionFactor, FactorLibrary


class FactorNotFoundError(LookupError):
    pass


@dataclass
class FactorMatch:
    factor: EmissionFactor
    score: int
    reasons: list[str]


def _score(factor: EmissionFactor, *, country: str, period: date,
           method: str | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if country and factor.country == country:
        score += 100
        reasons.append(f"exact country match ({country})")
    elif factor.country in ("GLOBAL", "", None):
        score += 10
        reasons.append("global fallback factor")
    else:
        return -1, ["country mismatch"]

    if factor.valid_from <= period and (factor.valid_to is None or factor.valid_to >= period):
        score += 50
        reasons.append(f"valid for period {period.isoformat()}")
    else:
        return -1, ["outside validity window"]

    if method and factor.method == method:
        score += 30
        reasons.append(f"method match ({method})")
    elif method and factor.method not in (method, "", None):
        score -= 5
        reasons.append(f"method differs (factor is {factor.method})")

    # Prefer the factor whose validity window starts closest to the period.
    score += max(0, 10 - abs(period.year - factor.valid_from.year))
    # Lower uncertainty wins ties.
    score += max(0, int(10 - factor.uncertainty_pct / 5))
    return score, reasons


def resolve(
    db: Session,
    *,
    activity_key: str,
    country: str,
    period: date,
    method: str | None = None,
    library_id: int | None = None,
    scope: str | None = None,
) -> FactorMatch:
    """Pick the single factor to use, or raise with an explanation."""
    stmt = select(EmissionFactor).where(EmissionFactor.activity_key == activity_key)
    if library_id is not None:
        stmt = stmt.where(EmissionFactor.library_id == library_id)
    if scope:
        stmt = stmt.where(EmissionFactor.scope == scope)
    candidates = list(db.scalars(stmt))
    if not candidates:
        raise FactorNotFoundError(
            f"No emission factor for activity_key='{activity_key}'"
            + (f" in library {library_id}" if library_id else "")
        )

    scored: list[FactorMatch] = []
    for f in candidates:
        s, reasons = _score(f, country=country, period=period, method=method)
        if s >= 0:
            scored.append(FactorMatch(f, s, reasons))

    if not scored:
        raise FactorNotFoundError(
            f"No emission factor for '{activity_key}' valid in {country} at {period.isoformat()}"
        )

    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[0]


def alternatives(
    db: Session, *, activity_key: str, country: str, period: date,
    method: str | None = None, library_id: int | None = None, limit: int = 3,
) -> list[dict]:
    """The runners-up, recorded in lineage so factor choice is auditable."""
    stmt = select(EmissionFactor).where(EmissionFactor.activity_key == activity_key)
    if library_id is not None:
        stmt = stmt.where(EmissionFactor.library_id == library_id)
    out = []
    for f in db.scalars(stmt):
        s, reasons = _score(f, country=country, period=period, method=method)
        out.append({
            "factor_id": f.id, "name": f.name, "country": f.country,
            "value_kgco2e": f.value_kgco2e, "unit": f.unit,
            "score": s, "reasons": reasons,
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out[:limit]


def default_library(db: Session) -> FactorLibrary:
    lib = db.scalars(select(FactorLibrary).where(FactorLibrary.is_default.is_(True))).first()
    if lib is None:
        lib = db.scalars(select(FactorLibrary)).first()
    if lib is None:
        raise FactorNotFoundError("No factor library configured")
    return lib


def locked_libraries(db: Session) -> list[FactorLibrary]:
    return list(db.scalars(select(FactorLibrary).where(FactorLibrary.is_locked.is_(True))))
