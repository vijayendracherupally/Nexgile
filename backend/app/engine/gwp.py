"""Global Warming Potentials (FR-3.A.4).

The GWP set is part of the methodology version (FR-7.3): changing AR5 -> AR6
changes every reported number, so it is stored on the Calculation row and any
change triggers a recalculation impact analysis.
"""
from __future__ import annotations

GWP_SETS: dict[str, dict[str, float]] = {
    "AR4": {
        "CO2": 1.0, "CH4": 25.0, "CH4_fossil": 25.0, "CH4_biogenic": 25.0,
        "N2O": 298.0, "SF6": 22800.0, "NF3": 17200.0,
        "HFC-23": 14800.0, "HFC-32": 675.0, "HFC-125": 3500.0, "HFC-134a": 1430.0,
        "HFC-143a": 4470.0, "HFC-152a": 124.0, "R-404A": 3922.0, "R-410A": 2088.0,
        "R-407C": 1774.0, "CF4": 7390.0, "C2F6": 12200.0,
    },
    "AR5": {
        "CO2": 1.0, "CH4": 28.0, "CH4_fossil": 30.0, "CH4_biogenic": 28.0,
        "N2O": 265.0, "SF6": 23500.0, "NF3": 16100.0,
        "HFC-23": 12400.0, "HFC-32": 677.0, "HFC-125": 3170.0, "HFC-134a": 1300.0,
        "HFC-143a": 4800.0, "HFC-152a": 138.0, "R-404A": 3943.0, "R-410A": 1924.0,
        "R-407C": 1624.0, "CF4": 6630.0, "C2F6": 11100.0,
    },
    "AR6": {
        "CO2": 1.0, "CH4": 29.8, "CH4_fossil": 29.8, "CH4_biogenic": 27.0,
        "N2O": 273.0, "SF6": 25200.0, "NF3": 17400.0,
        "HFC-23": 14600.0, "HFC-32": 771.0, "HFC-125": 3740.0, "HFC-134a": 1530.0,
        "HFC-143a": 5810.0, "HFC-152a": 164.0, "R-404A": 4728.0, "R-410A": 2256.0,
        "R-407C": 1908.0, "CF4": 7380.0, "C2F6": 12400.0,
    },
}

DEFAULT_SET = "AR6"


class UnknownGasError(KeyError):
    pass


def gwp(gas: str, gwp_set: str = DEFAULT_SET) -> float:
    table = GWP_SETS.get(gwp_set)
    if table is None:
        raise UnknownGasError(f"Unknown GWP set '{gwp_set}'")
    if gas not in table:
        raise UnknownGasError(f"Gas '{gas}' not in GWP set '{gwp_set}'")
    return table[gas]


def to_co2e(gas_masses_kg: dict[str, float], gwp_set: str = DEFAULT_SET) -> tuple[float, dict]:
    """Convert a per-gas mass breakdown into CO2e, returning the working."""
    total = 0.0
    detail: dict[str, dict] = {}
    for gas, mass in gas_masses_kg.items():
        if gas == "CO2e":  # already aggregated by the factor provider
            total += mass
            detail[gas] = {"mass_kg": mass, "gwp": 1.0, "co2e_kg": mass}
            continue
        g = gwp(gas, gwp_set)
        co2e = mass * g
        total += co2e
        detail[gas] = {"mass_kg": mass, "gwp": g, "co2e_kg": co2e}
    return total, detail


def available_sets() -> list[str]:
    return list(GWP_SETS.keys())
