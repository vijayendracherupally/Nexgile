"""Unit conversion (FR-3.A.4).

Every conversion returns the *chain* it used, because FR-7.2 requires the unit
conversion to be part of the stored lineage - not recomputed later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Base unit per dimension. All factors within a dimension are expressed
# relative to the base.
BASE_UNITS = {
    "energy": "kWh",
    "volume": "L",
    "mass": "kg",
    "distance": "km",
    "freight": "tkm",
    "passenger": "pkm",
    "currency": "EUR",
    "area": "m2",
    "count": "unit",
    "time": "h",
}

CONVERSIONS: dict[str, dict[str, float]] = {
    "energy": {
        "kWh": 1.0, "MWh": 1000.0, "GWh": 1_000_000.0, "Wh": 0.001,
        "MJ": 0.2777777778, "GJ": 277.7777778, "TJ": 277_777.7778,
        "therm": 29.30071, "MMBtu": 293.07107, "BTU": 0.000293071,
        "kcal": 0.001162222, "toe": 11630.0,
    },
    "volume": {
        "L": 1.0, "litre": 1.0, "liter": 1.0, "mL": 0.001, "m3": 1000.0,
        "gal_us": 3.785412, "gal_uk": 4.546092, "bbl": 158.9873, "ft3": 28.31685,
    },
    "mass": {
        "kg": 1.0, "g": 0.001, "mg": 1e-6, "t": 1000.0, "tonne": 1000.0,
        "kt": 1_000_000.0, "lb": 0.4535924, "short_ton": 907.1847, "long_ton": 1016.047,
    },
    "distance": {
        "km": 1.0, "m": 0.001, "mi": 1.609344, "nmi": 1.852, "ft": 0.0003048,
    },
    "freight": {
        "tkm": 1.0, "tonne_km": 1.0, "kgkm": 0.001, "t_mi": 1.609344, "TEU_km": 10.0,
    },
    "passenger": {"pkm": 1.0, "passenger_km": 1.0, "p_mi": 1.609344},
    "area": {"m2": 1.0, "ft2": 0.09290304, "ha": 10000.0, "km2": 1_000_000.0},
    "count": {"unit": 1.0, "piece": 1.0, "each": 1.0, "night": 1.0, "FTE": 1.0},
    "time": {"h": 1.0, "min": 1 / 60, "s": 1 / 3600, "day": 24.0, "year": 8760.0},
    # Currency is handled separately - rates change over time.
    "currency": {"EUR": 1.0},
}

# Indicative FX to EUR. In production these come from the External Data
# connectors (FR-5.3 commodity indices / rates).
FX_TO_EUR = {
    "EUR": 1.0, "USD": 0.92, "GBP": 1.17, "CHF": 1.04, "JPY": 0.0061,
    "CNY": 0.127, "INR": 0.011, "BRL": 0.169, "MXN": 0.050, "CAD": 0.673,
    "AUD": 0.607, "SEK": 0.087, "PLN": 0.232, "TRY": 0.027, "KRW": 0.00067,
    "ZAR": 0.050, "SGD": 0.685, "NOK": 0.086, "DKK": 0.134, "CZK": 0.040,
}

# Default densities (kg per litre) for cross-dimension conversion.
DENSITY_KG_PER_L = {
    "diesel": 0.832, "petrol": 0.745, "gasoline": 0.745, "kerosene": 0.800,
    "jet_fuel": 0.800, "fuel_oil": 0.940, "lpg": 0.540, "biodiesel": 0.880,
    "ethanol": 0.789, "water": 1.0, "crude_oil": 0.870,
}


class UnitConversionError(ValueError):
    pass


@dataclass
class ConversionResult:
    quantity: float
    unit: str
    chain: list[dict] = field(default_factory=list)


def dimension_of(unit: str) -> str | None:
    for dim, table in CONVERSIONS.items():
        if unit in table:
            return dim
    if unit in FX_TO_EUR:
        return "currency"
    return None


def normalize(
    quantity: float,
    from_unit: str,
    to_unit: str,
    *,
    substance: str | None = None,
) -> ConversionResult:
    """Convert `quantity` from_unit -> to_unit, recording every step."""
    chain: list[dict] = []
    if from_unit == to_unit:
        chain.append({"step": "identity", "from": from_unit, "to": to_unit, "factor": 1.0})
        return ConversionResult(quantity, to_unit, chain)

    from_dim, to_dim = dimension_of(from_unit), dimension_of(to_unit)
    if from_dim is None:
        raise UnitConversionError(f"Unknown unit '{from_unit}'")
    if to_dim is None:
        raise UnitConversionError(f"Unknown unit '{to_unit}'")

    value = quantity

    if from_dim == "currency" or to_dim == "currency":
        if from_dim != to_dim:
            raise UnitConversionError(f"Cannot convert {from_unit} to {to_unit}")
        rate_from = FX_TO_EUR.get(from_unit)
        rate_to = FX_TO_EUR.get(to_unit)
        if rate_from is None or rate_to is None:
            raise UnitConversionError(f"No FX rate for {from_unit}->{to_unit}")
        value = value * rate_from / rate_to
        chain.append({"step": "fx", "from": from_unit, "to": to_unit,
                      "factor": rate_from / rate_to})
        return ConversionResult(value, to_unit, chain)

    if from_dim != to_dim:
        # Cross-dimension is only legal with a documented density (volume<->mass).
        key = (substance or "").lower()
        density = DENSITY_KG_PER_L.get(key)
        if density is None or {from_dim, to_dim} != {"volume", "mass"}:
            raise UnitConversionError(
                f"Cannot convert {from_unit} ({from_dim}) to {to_unit} ({to_dim})"
                + ("" if substance else " - no substance given for density lookup")
            )
        # to base of source dimension first
        v_base = value * CONVERSIONS[from_dim][from_unit]
        chain.append({"step": "to_base", "from": from_unit, "to": BASE_UNITS[from_dim],
                      "factor": CONVERSIONS[from_dim][from_unit]})
        if from_dim == "volume":
            v_base *= density
            chain.append({"step": "density", "substance": key, "from": "L", "to": "kg",
                          "factor": density})
        else:
            v_base /= density
            chain.append({"step": "density", "substance": key, "from": "kg", "to": "L",
                          "factor": 1 / density})
        value = v_base / CONVERSIONS[to_dim][to_unit]
        chain.append({"step": "from_base", "from": BASE_UNITS[to_dim], "to": to_unit,
                      "factor": 1 / CONVERSIONS[to_dim][to_unit]})
        return ConversionResult(value, to_unit, chain)

    f_from = CONVERSIONS[from_dim][from_unit]
    f_to = CONVERSIONS[to_dim][to_unit]
    value = value * f_from / f_to
    chain.append({"step": "to_base", "from": from_unit, "to": BASE_UNITS[from_dim], "factor": f_from})
    chain.append({"step": "from_base", "from": BASE_UNITS[to_dim], "to": to_unit, "factor": 1 / f_to})
    return ConversionResult(value, to_unit, chain)


def known_units() -> dict[str, list[str]]:
    out = {dim: sorted(table.keys()) for dim, table in CONVERSIONS.items()}
    out["currency"] = sorted(FX_TO_EUR.keys())
    return out
