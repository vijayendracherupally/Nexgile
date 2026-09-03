"""Product LCA / PCF computation (FR-3.B).

Walks the multi-level BOM, the process model, the packaging, the multimodal
route set and the end-of-life scenario, and produces a stage-resolved footprint
with assumptions, uncertainty and sensitivity - the inputs ISO 14067 reporting
needs (FR-3.B.4).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import LCABoundary, PCFStatus
from app.domain.models import (
    BOM, BOMItem, Entity, Facility, FunctionalUnit, Material, PCF, Packaging,
    Process, Product, Route, Supplier,
)
from app.engine import factors as factor_engine
from app.engine import uncertainty as unc_engine
from app.engine import units

# Transport intensity in kgCO2e per tonne-km, used when no library factor exists.
TRANSPORT_FALLBACK = {
    "road": 0.11, "rail": 0.028, "sea": 0.011, "air": 0.60, "inland_waterway": 0.031,
}
WAREHOUSE_KGCO2E_PER_TONNE_DAY = 0.012

# End-of-life treatment intensities (kgCO2e per kg of product).
EOL_FACTORS = {
    "landfill": 0.58, "incineration": 1.35, "incineration_energy_recovery": 0.92,
    "recycling": -0.42, "composting": 0.18, "reuse": -0.60, "mixed": 0.31,
}

STAGES = ["raw_materials", "inbound_logistics", "manufacturing", "packaging",
          "outbound_logistics", "use_phase", "end_of_life"]


class LCAError(ValueError):
    pass


def _factor_value(db: Session, activity_key: str, country: str, period: date,
                  fallback: float | None = None) -> tuple[float, str, dict | None]:
    """Resolve a factor, falling back to a documented default when the library
    has no entry - the fallback is always recorded as an assumption."""
    try:
        match = factor_engine.resolve(db, activity_key=activity_key, country=country,
                                      period=period)
        f = match.factor
        return f.value_kgco2e, f.unit, {
            "factor_id": f.id, "name": f.name, "library_id": f.library_id,
            "value": f.value_kgco2e, "unit": f.unit, "country": f.country,
            "uncertainty_pct": f.uncertainty_pct,
        }
    except factor_engine.FactorNotFoundError:
        if fallback is None:
            raise
        return fallback, "kg", None


def _bom_tree(db: Session, bom_id: int) -> list[BOMItem]:
    return list(db.scalars(
        select(BOMItem).where(BOMItem.bom_id == bom_id, BOMItem.is_alternative.is_(False))
        .order_by(BOMItem.level, BOMItem.id)
    ))


def compute_pcf(
    db: Session,
    product: Product,
    *,
    boundary: str = LCABoundary.CRADLE_TO_GATE,
    allocation_basis: str = "mass",
    reference_period: int | None = None,
    end_of_life_scenario: str = "mixed",
    scenario_id: int | None = None,
    material_substitutions: dict[int, int] | None = None,
    include_use_phase_kwh_per_year: float | None = None,
) -> dict:
    """Compute one product footprint. Pure computation - persists nothing."""
    period_year = reference_period or date.today().year
    period = date(period_year, 1, 1)
    entity = db.get(Entity, product.entity_id)
    country = entity.country if entity and entity.country else "GLOBAL"

    assumptions: list[str] = []
    lineage_items: list[dict] = []
    stages: dict[str, float] = {s: 0.0 for s in STAGES}
    drivers: list[dict] = []
    uncertainties: list[float] = []
    substitutions = material_substitutions or {}

    # ---- raw materials (multi-level BOM, FR-3.B.1) ------------------------
    bom = db.scalars(
        select(BOM).where(BOM.product_id == product.id, BOM.is_active.is_(True))
        .order_by(BOM.id.desc())
    ).first()
    total_material_mass = 0.0
    if bom:
        for item in _bom_tree(db, bom.id):
            material_id = substitutions.get(item.id, item.material_id)
            material = db.get(Material, material_id) if material_id else None
            if material is None:
                assumptions.append(
                    f"BOM item '{item.component_name}' has no material assigned; excluded."
                )
                continue
            if material_id != item.material_id:
                assumptions.append(
                    f"Alternative-material scenario: '{item.component_name}' modelled as "
                    f"'{material.name}'."
                )
            mass = item.mass_kg or (item.quantity if item.unit == "kg" else 0.0)
            # Scrap increases the mass that must be purchased (FR-3.B.2).
            effective_mass = mass * (1 + (item.scrap_pct or 0.0) / 100.0)
            total_material_mass += effective_mass
            value, unit, detail = _factor_value(
                db, material.activity_key or "material.generic", country, period, fallback=2.1)
            if detail is None:
                assumptions.append(
                    f"No library factor for material '{material.name}'; generic 2.1 kgCO2e/kg used."
                )
                uncertainties.append(45.0)
            else:
                uncertainties.append(detail["uncertainty_pct"])
            qty = effective_mass
            if unit != "kg":
                try:
                    qty = units.normalize(effective_mass, "kg", unit,
                                          substance=material.name.lower()).quantity
                except units.UnitConversionError:
                    assumptions.append(
                        f"Could not convert kg to {unit} for '{material.name}'; kg assumed.")
            emissions = qty * value
            # Recycled content reduces the virgin burden proportionally.
            if material.recycled_content_pct:
                reduction = emissions * (material.recycled_content_pct / 100.0) * 0.6
                emissions -= reduction
                assumptions.append(
                    f"'{material.name}' carries {material.recycled_content_pct:g}% recycled "
                    "content; virgin burden reduced by 60% of that share."
                )
            stages["raw_materials"] += emissions
            supplier = db.get(Supplier, item.component_supplier_id) if item.component_supplier_id else None
            lineage_items.append({
                "stage": "raw_materials", "bom_item_id": item.id, "level": item.level,
                "component": item.component_name, "material": material.name,
                "supplier": supplier.name if supplier else None,
                "mass_kg": round(effective_mass, 5),
                "scrap_pct": item.scrap_pct, "factor": detail,
                "factor_value_used": value, "kgco2e": round(emissions, 5),
            })
            drivers.append({"name": f"{item.component_name} ({material.name})",
                            "contribution": emissions})
    else:
        assumptions.append("No active BOM found; raw-material stage is zero.")

    # ---- inbound logistics + outbound logistics (FR-3.B.2) ----------------
    for route in db.scalars(select(Route).where(Route.product_id == product.id)):
        payload = route.payload_tonnes or (total_material_mass / 1000 or 0.001)
        load = max(0.1, (route.load_factor_pct or 80.0) / 100.0)
        tkm = payload * route.distance_km / load
        value, _unit, detail = _factor_value(
            db, f"transport.{route.mode}", country, period,
            fallback=TRANSPORT_FALLBACK.get(route.mode, 0.11))
        if detail is None:
            assumptions.append(
                f"No library factor for {route.mode} freight; "
                f"{TRANSPORT_FALLBACK.get(route.mode, 0.11)} kgCO2e/tkm default used.")
            uncertainties.append(35.0)
        else:
            uncertainties.append(detail["uncertainty_pct"])
        emissions = tkm * value
        warehousing = payload * (route.warehouse_days or 0.0) * WAREHOUSE_KGCO2E_PER_TONNE_DAY
        emissions += warehousing
        stage = "outbound_logistics" if route.stage == "outbound" else "inbound_logistics"
        stages[stage] += emissions
        lineage_items.append({
            "stage": stage, "route_id": route.id, "mode": route.mode,
            "origin": route.origin, "destination": route.destination,
            "distance_km": route.distance_km, "payload_tonnes": payload,
            "load_factor_pct": route.load_factor_pct, "tkm": round(tkm, 4),
            "warehouse_days": route.warehouse_days,
            "warehousing_kgco2e": round(warehousing, 5),
            "factor": detail, "factor_value_used": value, "kgco2e": round(emissions, 5),
        })
        drivers.append({"name": f"{route.mode} {route.origin}->{route.destination}",
                        "contribution": emissions})

    # ---- manufacturing (FR-3.B.2) -----------------------------------------
    for proc in db.scalars(
        select(Process).where(Process.product_id == product.id).order_by(Process.sequence)
    ):
        fac = db.get(Facility, proc.facility_id) if proc.facility_id else None
        proc_country = fac.country if fac and fac.country else country
        grid_value, _u, grid_detail = _factor_value(
            db, "electricity.grid", proc_country, period, fallback=0.35)
        if grid_detail is None:
            assumptions.append(
                f"No grid factor for {proc_country}; 0.35 kgCO2e/kWh default used.")
            uncertainties.append(30.0)
        else:
            uncertainties.append(grid_detail["uncertainty_pct"])

        # Yield / scrap / defects all raise the energy actually consumed per
        # saleable unit (FR-3.B.2).
        yield_factor = 100.0 / max(1.0, proc.yield_pct or 100.0)
        loss_factor = 1 + (proc.scrap_rate_pct or 0.0) / 100.0 + (proc.defect_rate_pct or 0.0) / 100.0
        multiplier = yield_factor * loss_factor

        electricity = (proc.energy_kwh_per_unit or 0.0) * multiplier * grid_value
        thermal_kwh = (proc.thermal_mj_per_unit or 0.0) / 3.6 * multiplier
        thermal_value, _tu, thermal_detail = _factor_value(
            db, "natural_gas.stationary", proc_country, period, fallback=0.202)
        thermal = thermal_kwh * thermal_value
        direct = (proc.direct_emissions_kgco2e or 0.0) * multiplier
        emissions = electricity + thermal + direct
        stages["manufacturing"] += emissions
        lineage_items.append({
            "stage": "manufacturing", "process_id": proc.id, "process": proc.name,
            "production_mode": proc.production_mode, "facility": fac.name if fac else None,
            "energy_kwh_per_unit": proc.energy_kwh_per_unit,
            "thermal_mj_per_unit": proc.thermal_mj_per_unit,
            "scrap_rate_pct": proc.scrap_rate_pct, "defect_rate_pct": proc.defect_rate_pct,
            "yield_pct": proc.yield_pct, "loss_multiplier": round(multiplier, 4),
            "grid_factor": grid_detail, "electricity_kgco2e": round(electricity, 5),
            "thermal_kgco2e": round(thermal, 5), "direct_kgco2e": round(direct, 5),
            "kgco2e": round(emissions, 5),
        })
        drivers.append({"name": f"Process: {proc.name}", "contribution": emissions})

    # ---- packaging ---------------------------------------------------------
    packaging_mass = 0.0
    for pack in db.scalars(select(Packaging).where(Packaging.product_id == product.id)):
        material = db.get(Material, pack.material_id) if pack.material_id else None
        key = material.activity_key if material and material.activity_key else "material.generic"
        value, _pu, detail = _factor_value(db, key, country, period, fallback=1.8)
        if detail is None:
            uncertainties.append(40.0)
            assumptions.append(
                f"No library factor for packaging '{pack.name}'; 1.8 kgCO2e/kg default used.")
        else:
            uncertainties.append(detail["uncertainty_pct"])
        mass = pack.mass_kg or 0.0
        # Reusable packaging amortises across its reuse cycles.
        cycles = max(1, pack.reuse_cycles or 1)
        emissions = mass * value / cycles
        if pack.recycled_content_pct:
            emissions *= (1 - (pack.recycled_content_pct / 100.0) * 0.6)
        packaging_mass += mass
        stages["packaging"] += emissions
        lineage_items.append({
            "stage": "packaging", "packaging_id": pack.id, "name": pack.name,
            "level": pack.level, "mass_kg": mass, "reuse_cycles": pack.reuse_cycles,
            "recycled_content_pct": pack.recycled_content_pct,
            "factor": detail, "factor_value_used": value, "kgco2e": round(emissions, 5),
        })
        drivers.append({"name": f"Packaging: {pack.name}", "contribution": emissions})

    # ---- use phase and end of life (cradle-to-grave only, FR-3.B.3) -------
    product_mass = product.mass_kg or total_material_mass or 0.0
    if boundary == LCABoundary.CRADLE_TO_GRAVE:
        annual_kwh = include_use_phase_kwh_per_year
        if annual_kwh:
            grid_value, _u2, grid_detail = _factor_value(
                db, "electricity.grid", country, period, fallback=0.35)
            use_emissions = annual_kwh * (product.lifetime_years or 1.0) * grid_value
            stages["use_phase"] += use_emissions
            lineage_items.append({
                "stage": "use_phase", "annual_kwh": annual_kwh,
                "lifetime_years": product.lifetime_years, "factor": grid_detail,
                "kgco2e": round(use_emissions, 5),
            })
            drivers.append({"name": "Use phase electricity", "contribution": use_emissions})
            assumptions.append(
                f"Use phase modelled at {annual_kwh:g} kWh/year over "
                f"{product.lifetime_years:g} years on the {country} grid."
            )
        else:
            assumptions.append(
                "Cradle-to-grave boundary selected but no use-phase energy supplied; "
                "use phase reported as zero."
            )
        eol_intensity = EOL_FACTORS.get(end_of_life_scenario, EOL_FACTORS["mixed"])
        eol_mass = product_mass + packaging_mass
        eol = eol_mass * eol_intensity
        stages["end_of_life"] += eol
        lineage_items.append({
            "stage": "end_of_life", "scenario": end_of_life_scenario,
            "mass_kg": round(eol_mass, 4), "intensity_kgco2e_per_kg": eol_intensity,
            "kgco2e": round(eol, 5),
        })
        drivers.append({"name": f"End-of-life ({end_of_life_scenario})", "contribution": eol})
        assumptions.append(
            f"End-of-life modelled as '{end_of_life_scenario}' at {eol_intensity} kgCO2e/kg; "
            "recycling credits are negative by convention."
        )
    elif boundary == LCABoundary.GATE_TO_GATE:
        # Only own operations count.
        for stage in ("raw_materials", "inbound_logistics", "outbound_logistics",
                      "use_phase", "end_of_life"):
            if stages[stage]:
                assumptions.append(
                    f"Gate-to-gate boundary: '{stage}' excluded from the reported total.")
            stages[stage] = 0.0

    total = sum(stages.values())

    # ---- functional unit ---------------------------------------------------
    fu = db.get(FunctionalUnit, product.functional_unit_id) if product.functional_unit_id else None
    fu_quantity = (fu.quantity if fu and fu.quantity else 1.0)
    per_fu = total / fu_quantity if fu_quantity else total

    # ---- circularity (FR-3.B.3) -------------------------------------------
    recycled_total, recyclable_mass, mass_seen = 0.0, 0.0, 0.0
    if bom:
        for item in _bom_tree(db, bom.id):
            material = db.get(Material, item.material_id) if item.material_id else None
            if material is None:
                continue
            m = item.mass_kg or 0.0
            mass_seen += m
            recycled_total += m * (material.recycled_content_pct or 0.0) / 100.0
            if material.recyclable:
                recyclable_mass += m
    recycled_pct = (recycled_total / mass_seen * 100) if mass_seen else 0.0
    recyclability_pct = (recyclable_mass / mass_seen * 100) if mass_seen else 0.0
    circularity = round((recycled_pct + recyclability_pct) / 2, 2)

    # ---- uncertainty & sensitivity (FR-3.B.4) -----------------------------
    combined_uncertainty = (
        round((sum(u ** 2 for u in uncertainties) / len(uncertainties)) ** 0.5, 2)
        if uncertainties else 25.0
    )
    sensitivity = unc_engine.sensitivity(total, drivers, delta_pct=10.0)[:12]
    monte_carlo = unc_engine.monte_carlo(total, combined_uncertainty, iterations=5000)

    iso_ready = bool(
        bom and total > 0 and fu is not None
        and boundary in (LCABoundary.CRADLE_TO_GATE, LCABoundary.CRADLE_TO_GRAVE)
    )
    if not iso_ready:
        assumptions.append(
            "Not yet ISO 14067-ready: requires an active BOM, a declared functional unit "
            "and a cradle-to-gate or cradle-to-grave boundary."
        )

    return {
        "product_id": product.id,
        "sku": product.sku,
        "boundary": boundary,
        "allocation_basis": allocation_basis,
        "reference_period": period_year,
        "total_kgco2e": round(total, 5),
        "per_functional_unit_kgco2e": round(per_fu, 5),
        "functional_unit": {
            "id": fu.id if fu else None,
            "name": fu.name if fu else "1 product unit",
            "unit": fu.unit if fu else "unit",
            "quantity": fu_quantity,
        },
        "stage_breakdown": {k: round(v, 5) for k, v in stages.items()},
        "stage_shares_pct": {
            k: round(v / total * 100, 2) if total else 0.0 for k, v in stages.items()
        },
        "product_mass_kg": round(product_mass, 4),
        "packaging_mass_kg": round(packaging_mass, 4),
        "recycled_content_pct": round(recycled_pct, 2),
        "recyclability_pct": round(recyclability_pct, 2),
        "circularity_score": circularity,
        "end_of_life_scenario": end_of_life_scenario,
        "uncertainty_pct": combined_uncertainty,
        "sensitivity": sensitivity,
        "monte_carlo": monte_carlo,
        "assumptions": assumptions,
        "iso14067_ready": iso_ready,
        "scenario_id": scenario_id,
        "lineage": {
            "schema_version": "1.0",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "boundary": boundary,
            "country": country,
            "items": lineage_items,
            "stage_totals": {k: round(v, 5) for k, v in stages.items()},
            "assumptions": assumptions,
        },
    }


def persist_pcf(db: Session, product: Product, computed: dict, *,
                status: str = PCFStatus.CALCULATED) -> PCF:
    scenario_id = computed.get("scenario_id")
    scenario_filter = (PCF.scenario_id.is_(None) if scenario_id is None
                       else PCF.scenario_id == scenario_id)
    previous = db.scalars(
        select(PCF).where(PCF.product_id == product.id, scenario_filter)
        .order_by(PCF.version.desc())
    ).first()
    pcf = PCF(
        product_id=product.id,
        functional_unit_id=product.functional_unit_id,
        boundary=computed["boundary"],
        allocation_basis=computed["allocation_basis"],
        reference_period=computed["reference_period"],
        version=(previous.version + 1) if previous else 1,
        status=status,
        total_kgco2e=computed["total_kgco2e"],
        per_functional_unit_kgco2e=computed["per_functional_unit_kgco2e"],
        stage_breakdown=computed["stage_breakdown"],
        recycled_content_pct=computed["recycled_content_pct"],
        recyclability_pct=computed["recyclability_pct"],
        end_of_life_scenario=computed["end_of_life_scenario"],
        circularity_score=computed["circularity_score"],
        assumptions=computed["assumptions"],
        uncertainty_pct=computed["uncertainty_pct"],
        sensitivity=computed["sensitivity"],
        iso14067_ready=computed["iso14067_ready"],
        lineage=computed["lineage"],
        scenario_id=computed.get("scenario_id"),
    )
    db.add(pcf)
    db.flush()
    return pcf


def iso14067_report(db: Session, pcf: PCF) -> dict:
    """FR-3.B.4 - the report structure ISO 14067 expects."""
    product = db.get(Product, pcf.product_id)
    fu = db.get(FunctionalUnit, pcf.functional_unit_id) if pcf.functional_unit_id else None
    entity = db.get(Entity, product.entity_id) if product else None
    return {
        "standard": "ISO 14067:2018",
        "ready": pcf.iso14067_ready,
        "1_goal_and_scope": {
            "product": {"sku": product.sku, "name": product.name} if product else {},
            "declared_organization": entity.name if entity else "",
            "functional_unit": {
                "name": fu.name if fu else "1 product unit",
                "unit": fu.unit if fu else "unit",
                "quantity": fu.quantity if fu else 1.0,
            },
            "system_boundary": pcf.boundary,
            "reference_period": pcf.reference_period,
            "cut_off_criteria": "Flows below 1% of total mass excluded; sum of exclusions < 5%.",
            "allocation_procedure": pcf.allocation_basis,
        },
        "2_life_cycle_inventory": {
            "stage_breakdown_kgco2e": pcf.stage_breakdown,
            "data_sources": sorted({
                (item.get("factor") or {}).get("name", "process model")
                for item in (pcf.lineage or {}).get("items", [])
            }),
            "primary_data_share_pct": _primary_share(pcf),
        },
        "3_impact_assessment": {
            "indicator": "Climate change (GWP100)",
            "total_kgco2e": pcf.total_kgco2e,
            "per_functional_unit_kgco2e": pcf.per_functional_unit_kgco2e,
            "biogenic_kgco2e": pcf.biogenic_kgco2e,
        },
        "4_interpretation": {
            "assumptions": pcf.assumptions,
            "uncertainty_pct": pcf.uncertainty_pct,
            "sensitivity_analysis": pcf.sensitivity,
            "circularity": {
                "recycled_content_pct": pcf.recycled_content_pct,
                "recyclability_pct": pcf.recyclability_pct,
                "end_of_life_scenario": pcf.end_of_life_scenario,
                "circularity_score": pcf.circularity_score,
            },
        },
        "5_verification": {
            "status": pcf.status,
            "peer_reviewer": pcf.peer_reviewer,
            "peer_reviewed_at": pcf.peer_reviewed_at.isoformat() if pcf.peer_reviewed_at else None,
            "verifier": pcf.verifier,
            "verified_at": pcf.verified_at.isoformat() if pcf.verified_at else None,
            "certification_ref": pcf.certification_ref,
        },
        "lineage": pcf.lineage,
    }


def _primary_share(pcf: PCF) -> float:
    items = (pcf.lineage or {}).get("items", [])
    if not items:
        return 0.0
    with_factor = sum(1 for i in items if i.get("factor"))
    return round(with_factor / len(items) * 100, 1)


def exchange_payload(db: Session, pcf: PCF, fmt: str = "pact") -> dict:
    """FR-3.B.5 / FR-5.4 - B2B exchange in PACT or TfS shape."""
    product = db.get(Product, pcf.product_id)
    entity = db.get(Entity, product.entity_id) if product else None
    common = {
        "productId": product.sku if product else "",
        "productName": product.name if product else "",
        "companyName": entity.name if entity else "",
        "pcfExcludingBiogenic": pcf.per_functional_unit_kgco2e,
        "declaredUnit": "kilogram",
        "unitaryProductAmount": product.mass_kg if product else 1.0,
        "referencePeriodStart": f"{pcf.reference_period}-01-01T00:00:00Z",
        "referencePeriodEnd": f"{pcf.reference_period}-12-31T23:59:59Z",
        "boundaryProcessesDescription": pcf.boundary,
        "crossSectoralStandardsUsed": ["ISO Standard 14067"],
        "primaryDataShare": _primary_share(pcf),
    }
    if fmt.lower() == "tfs":
        return {
            "specVersion": "TfS PCF Guideline v3.0",
            "id": f"tfs-pcf-{pcf.id}",
            "version": pcf.version,
            "created": pcf.created_at.isoformat(),
            "status": pcf.status,
            "productFootprint": {
                **common,
                "dataQualityIndicators": {
                    "uncertaintyPercent": pcf.uncertainty_pct,
                    "recycledContentPercent": pcf.recycled_content_pct,
                },
                "verification": {
                    "assuranceStatus": pcf.status,
                    "verifier": pcf.verifier,
                },
            },
        }
    return {
        "specVersion": "PACT Pathfinder 2.2",
        "id": f"pact-pcf-{pcf.id}",
        "version": pcf.version,
        "created": pcf.created_at.isoformat(),
        "status": "Active" if pcf.status in (PCFStatus.VERIFIED, PCFStatus.CERTIFIED) else "Draft",
        "companyIds": [f"urn:decarbx:entity:{entity.id}" if entity else ""],
        "productIds": [f"urn:decarbx:sku:{product.sku}" if product else ""],
        "pcf": {
            **common,
            "fossilGhgEmissions": pcf.total_kgco2e,
            "biogenicCarbonEmissionsOtherThanCO2": pcf.biogenic_kgco2e,
            "dqi": {"coveragePercent": 100.0, "uncertaintyPercent": pcf.uncertainty_pct},
        },
    }
