"""Uncertainty, confidence and Monte Carlo (FR-3.A.4, FR-3.D.2, FR-7.4).

Uses the standard pedigree-matrix approach: data-quality indicators produce an
uncertainty factor, which combines with the factor's own uncertainty.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from app.domain.enums import MEASURED_ORIGINS, DataOrigin

# Pedigree scores 1 (best) .. 5 (worst) -> uncertainty contribution (%).
PEDIGREE_UNCERTAINTY = {
    "reliability":        {1: 0.0, 2: 5.0, 3: 10.0, 4: 20.0, 5: 30.0},
    "completeness":       {1: 0.0, 2: 3.0, 3: 6.0, 4: 12.0, 5: 20.0},
    "temporal":           {1: 0.0, 2: 4.0, 3: 8.0, 4: 15.0, 5: 25.0},
    "geographical":       {1: 0.0, 2: 4.0, 3: 8.0, 4: 15.0, 5: 25.0},
    "technological":      {1: 0.0, 2: 5.0, 3: 10.0, 4: 18.0, 5: 28.0},
}

ORIGIN_RELIABILITY = {
    DataOrigin.METER: 1, DataOrigin.SENSOR: 1, DataOrigin.TELEMATICS: 1,
    DataOrigin.INVOICE: 2, DataOrigin.SUPPLIER_PRIMARY: 2, DataOrigin.RECEIPT: 2,
    DataOrigin.ERP: 2, DataOrigin.SURVEY: 3, DataOrigin.SPEND: 4,
    DataOrigin.ESTIMATED: 4, DataOrigin.GAP_FILLED: 5,
}


@dataclass
class UncertaintyResult:
    uncertainty_pct: float
    confidence_score: float      # 0-100
    rating: str                  # A/B/C/D/E
    pedigree: dict
    components: dict


def rate(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "E"


def assess(
    *,
    data_origin: str,
    factor_uncertainty_pct: float,
    completeness_pct: float = 100.0,
    factor_country_matches: bool = True,
    factor_year_gap: int = 0,
    factor_technology_match: bool = True,
    evidence_present: bool = False,
) -> UncertaintyResult:
    """Combine data-quality indicators into an uncertainty and a 0-100 score."""
    reliability = ORIGIN_RELIABILITY.get(data_origin, 4)
    completeness = 1 if completeness_pct >= 99 else 2 if completeness_pct >= 90 \
        else 3 if completeness_pct >= 75 else 4 if completeness_pct >= 50 else 5
    temporal = 1 if factor_year_gap <= 1 else 2 if factor_year_gap <= 3 \
        else 3 if factor_year_gap <= 6 else 4 if factor_year_gap <= 10 else 5
    geographical = 1 if factor_country_matches else 4
    technological = 1 if factor_technology_match else 3

    pedigree = {
        "reliability": reliability, "completeness": completeness,
        "temporal": temporal, "geographical": geographical,
        "technological": technological,
    }
    contributions = {k: PEDIGREE_UNCERTAINTY[k][v] for k, v in pedigree.items()}

    # Uncertainties combine in quadrature, together with the factor's own.
    squares = sum(c ** 2 for c in contributions.values()) + factor_uncertainty_pct ** 2
    total = math.sqrt(squares)

    score = max(0.0, 100.0 - total)
    if data_origin in MEASURED_ORIGINS:
        score = min(100.0, score + 5.0)
    if evidence_present:
        score = min(100.0, score + 5.0)
    if data_origin == DataOrigin.GAP_FILLED:
        score = max(0.0, score - 10.0)

    return UncertaintyResult(
        uncertainty_pct=round(total, 2),
        confidence_score=round(score, 1),
        rating=rate(score),
        pedigree=pedigree,
        components={**contributions, "emission_factor": factor_uncertainty_pct},
    )


def monte_carlo(
    mean: float,
    uncertainty_pct: float,
    iterations: int = 10_000,
    distribution: str = "lognormal",
    seed: int | None = 42,
) -> dict:
    """FR-3.D.2 - Monte Carlo uncertainty on a single aggregate."""
    if mean == 0:
        return {"mean": 0.0, "p5": 0.0, "p50": 0.0, "p95": 0.0,
                "std_dev": 0.0, "iterations": 0, "distribution": distribution}
    rng = random.Random(seed)
    sigma_rel = max(uncertainty_pct, 0.001) / 100.0
    samples: list[float] = []
    if distribution == "lognormal":
        # Convert relative sd to lognormal sigma.
        sigma = math.sqrt(math.log(1 + sigma_rel ** 2))
        mu = math.log(abs(mean)) - 0.5 * sigma ** 2
        for _ in range(iterations):
            samples.append(math.copysign(math.exp(rng.gauss(mu, sigma)), mean))
    else:
        sd = abs(mean) * sigma_rel
        for _ in range(iterations):
            samples.append(rng.gauss(mean, sd))
    samples.sort()

    def pct(p: float) -> float:
        idx = min(len(samples) - 1, max(0, int(round(p * (len(samples) - 1)))))
        return samples[idx]

    m = sum(samples) / len(samples)
    var = sum((s - m) ** 2 for s in samples) / len(samples)
    return {
        "mean": round(m, 3),
        "p5": round(pct(0.05), 3),
        "p50": round(pct(0.50), 3),
        "p95": round(pct(0.95), 3),
        "std_dev": round(math.sqrt(var), 3),
        "iterations": iterations,
        "distribution": distribution,
        "histogram": _histogram(samples, 24),
    }


def _histogram(samples: list[float], bins: int) -> list[dict]:
    lo, hi = samples[0], samples[-1]
    if hi <= lo:
        return []
    width = (hi - lo) / bins
    counts = [0] * bins
    for s in samples:
        idx = min(bins - 1, int((s - lo) / width))
        counts[idx] += 1
    return [{"bin_start": round(lo + i * width, 3),
             "bin_end": round(lo + (i + 1) * width, 3),
             "count": c} for i, c in enumerate(counts)]


def sensitivity(base_value: float, drivers: list[dict], delta_pct: float = 10.0) -> list[dict]:
    """FR-3.D.2 / FR-3.B.4 - one-at-a-time sensitivity (tornado chart input).

    Each driver is {"name": str, "contribution": float} in absolute terms.
    """
    out = []
    for d in drivers:
        contribution = float(d.get("contribution", 0.0))
        swing = contribution * delta_pct / 100.0
        out.append({
            "driver": d.get("name", "unknown"),
            "contribution": round(contribution, 3),
            "share_pct": round(contribution / base_value * 100, 2) if base_value else 0.0,
            "low": round(base_value - swing, 3),
            "high": round(base_value + swing, 3),
            "swing": round(swing * 2, 3),
            "delta_pct": delta_pct,
        })
    out.sort(key=lambda x: abs(x["swing"]), reverse=True)
    return out
