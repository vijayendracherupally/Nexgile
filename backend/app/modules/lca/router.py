"""B) Product LCA & PCF - FR-3.B.1 to FR-3.B.5."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import ScenarioContext, assert_visible, get_scenario_context, scoped
from app.core.serialize import page_response, rows, to_dict
from app.domain.enums import LCABoundary, PCFStatus, ProductionMode, TransportMode
from app.domain.models import (
    BOM, BOMItem, Evidence, FunctionalUnit, Material, PCF, Packaging, Process,
    Product, Route, Supplier,
)
from app.modules.lca import service

router = APIRouter(prefix="/lca", tags=["B) Product LCA & PCF"])


# ---------------------------------------------------------------------------
# Products, BOM, process model
# ---------------------------------------------------------------------------

@router.get("/products")
def list_products(
    entity_id: int | None = None, category: str | None = None, q: str | None = None,
    page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Product).order_by(Product.sku)
    if entity_id:
        stmt = stmt.where(Product.entity_id == entity_id)
    if category:
        stmt = stmt.where(Product.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Product.name.like(like) | Product.sku.like(like))

    def mapper(prod: Product) -> dict:
        pcf = db.scalars(
            select(PCF).where(PCF.product_id == prod.id, PCF.scenario_id.is_(None))
            .order_by(PCF.version.desc())
        ).first()
        return to_dict(prod, extra={
            "latest_pcf_id": pcf.id if pcf else None,
            "pcf_kgco2e": pcf.total_kgco2e if pcf else None,
            "pcf_per_functional_unit": pcf.per_functional_unit_kgco2e if pcf else None,
            "pcf_status": pcf.status if pcf else "not_calculated",
            "pcf_boundary": pcf.boundary if pcf else None,
            "iso14067_ready": pcf.iso14067_ready if pcf else False,
        })

    return page_response(db, scoped(stmt, Product, p), page=page, page_size=page_size,
                         mapper=mapper)


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db),
                p: Principal = Depends(get_principal)):
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(404, "Product not found")
    assert_visible(p, object_type="product", object_id=product_id)
    fu = db.get(FunctionalUnit, prod.functional_unit_id) if prod.functional_unit_id else None
    return to_dict(prod, extra={"functional_unit": to_dict(fu) if fu else None})


@router.get("/products/{product_id}/bom")
def get_bom(product_id: int, db: Session = Depends(get_db),
            p: Principal = Depends(get_principal)):
    """FR-3.B.1 - multi-level BOM with material composition, component-supplier
    mapping and alternative-material options."""
    assert_visible(p, object_type="product", object_id=product_id)
    bom = db.scalars(
        select(BOM).where(BOM.product_id == product_id, BOM.is_active.is_(True))
        .order_by(BOM.id.desc())
    ).first()
    if bom is None:
        return {"bom": None, "items": [], "levels": 0}

    items = list(db.scalars(select(BOMItem).where(BOMItem.bom_id == bom.id)
                            .order_by(BOMItem.level, BOMItem.id)))

    def enrich(i: BOMItem) -> dict:
        mat = db.get(Material, i.material_id) if i.material_id else None
        sup = db.get(Supplier, i.component_supplier_id) if i.component_supplier_id else None
        alts = [
            to_dict(a, extra={"material_name": (db.get(Material, a.material_id).name
                                                if a.material_id else None)})
            for a in items if a.alternative_for_id == i.id
        ]
        return to_dict(i, extra={
            "material_name": mat.name if mat else None,
            "material_class": mat.material_class if mat else None,
            "recycled_content_pct": mat.recycled_content_pct if mat else None,
            "recyclable": mat.recyclable if mat else None,
            "supplier_name": sup.name if sup else None,
            "supplier_tier": sup.tier if sup else None,
            "alternatives": alts,
            "children": [],
        })

    nodes = {i.id: enrich(i) for i in items if not i.is_alternative}
    roots = []
    for i in items:
        if i.is_alternative:
            continue
        node = nodes[i.id]
        if i.parent_item_id and i.parent_item_id in nodes:
            nodes[i.parent_item_id]["children"].append(node)
        else:
            roots.append(node)
    return {
        "bom": to_dict(bom),
        "items": roots,
        "flat": [nodes[i.id] for i in items if not i.is_alternative],
        "levels": max((i.level for i in items), default=0),
        "total_mass_kg": round(sum(i.mass_kg or 0 for i in items if not i.is_alternative), 4),
    }


@router.get("/products/{product_id}/processes")
def list_processes(product_id: int, db: Session = Depends(get_db)):
    """FR-3.B.2 - the process model."""
    return rows(db.scalars(select(Process).where(Process.product_id == product_id)
                           .order_by(Process.sequence)))


@router.get("/products/{product_id}/routes")
def list_routes(product_id: int, db: Session = Depends(get_db)):
    """FR-3.B.2 - multimodal logistics and warehousing."""
    return rows(db.scalars(select(Route).where(Route.product_id == product_id)
                           .order_by(Route.stage, Route.leg_sequence)))


@router.get("/products/{product_id}/packaging")
def list_packaging(product_id: int, db: Session = Depends(get_db)):
    return rows(db.scalars(select(Packaging).where(Packaging.product_id == product_id)))


@router.get("/materials")
def list_materials(q: str | None = None, alternatives_only: bool = False,
                   db: Session = Depends(get_db)):
    stmt = select(Material).order_by(Material.name)
    if q:
        stmt = stmt.where(Material.name.like(f"%{q}%"))
    if alternatives_only:
        stmt = stmt.where(Material.is_alternative.is_(True))
    return rows(db.scalars(stmt))


@router.get("/functional-units")
def list_functional_units(db: Session = Depends(get_db)):
    return rows(db.scalars(select(FunctionalUnit).order_by(FunctionalUnit.name)))


@router.get("/reference/vocabulary")
def lca_vocabulary():
    return {
        "boundaries": [b.value for b in LCABoundary],
        "pcf_statuses": [s.value for s in PCFStatus],
        "transport_modes": [m.value for m in TransportMode],
        "production_modes": [m.value for m in ProductionMode],
        "end_of_life_scenarios": list(service.EOL_FACTORS.keys()),
        "stages": service.STAGES,
        "exchange_formats": ["pact", "tfs"],
    }


# ---------------------------------------------------------------------------
# FR-3.B.3 / .4  PCF computation
# ---------------------------------------------------------------------------

class PCFRequest(BaseModel):
    boundary: str = LCABoundary.CRADLE_TO_GATE
    allocation_basis: str = "mass"
    reference_period: int | None = None
    end_of_life_scenario: str = "mixed"
    use_phase_kwh_per_year: float | None = None
    material_substitutions: dict[int, int] = Field(default_factory=dict)
    persist: bool = True


@router.post("/products/{product_id}/pcf/calculate")
def calculate_pcf(
    product_id: int, payload: PCFRequest,
    db: Session = Depends(get_db), p: Principal = Depends(require("lca.write")),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(404, "Product not found")
    assert_visible(p, object_type="product", object_id=product_id)
    computed = service.compute_pcf(
        db, prod,
        boundary=payload.boundary,
        allocation_basis=payload.allocation_basis,
        reference_period=payload.reference_period,
        end_of_life_scenario=payload.end_of_life_scenario,
        scenario_id=ctx.scenario_id,
        material_substitutions=payload.material_substitutions,
        include_use_phase_kwh_per_year=payload.use_phase_kwh_per_year,
    )
    pcf_id = None
    if payload.persist:
        pcf = service.persist_pcf(db, prod, computed)
        pcf_id = pcf.id
        db.commit()
    return {**computed, "pcf_id": pcf_id, "is_sandbox": ctx.is_sandbox}


@router.get("/pcf")
def list_pcfs(
    product_id: int | None = None, status: str | None = None,
    page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    stmt = select(PCF).order_by(PCF.id.desc())
    if product_id:
        stmt = stmt.where(PCF.product_id == product_id)
    if status:
        stmt = stmt.where(PCF.status == status)
    stmt = ctx.filter(scoped(stmt, PCF, p), PCF)

    def mapper(pcf: PCF) -> dict:
        prod = db.get(Product, pcf.product_id)
        return to_dict(pcf, exclude={"lineage"}, extra={
            "sku": prod.sku if prod else None,
            "product_name": prod.name if prod else None,
        })

    return page_response(db, stmt, page=page, page_size=page_size, mapper=mapper)


@router.get("/pcf/{pcf_id}")
def get_pcf(pcf_id: int, db: Session = Depends(get_db)):
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    prod = db.get(Product, pcf.product_id)
    return to_dict(pcf, extra={"sku": prod.sku if prod else None,
                               "product_name": prod.name if prod else None})


@router.get("/pcf/{pcf_id}/lineage")
def pcf_lineage(pcf_id: int, db: Session = Depends(get_db)):
    """FR-7.2 applied to product footprints."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    return {
        "pcf_id": pcf.id, "version": pcf.version, "status": pcf.status,
        "total_kgco2e": pcf.total_kgco2e, "boundary": pcf.boundary,
        "allocation_basis": pcf.allocation_basis,
        "assumptions": pcf.assumptions, "uncertainty_pct": pcf.uncertainty_pct,
        "sensitivity": pcf.sensitivity, "lineage": pcf.lineage,
        "evidence": rows(db.scalars(select(Evidence).where(
            Evidence.object_type == "pcf", Evidence.object_id == pcf.id))),
    }


@router.get("/pcf/{pcf_id}/iso14067-report")
def iso_report(pcf_id: int, db: Session = Depends(get_db)):
    """FR-3.B.4 - ISO 14067-ready report structure."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    return service.iso14067_report(db, pcf)


@router.get("/pcf/{pcf_id}/exchange")
def pcf_exchange(pcf_id: int, format: str = Query(default="pact", pattern="^(pact|tfs)$"),
                 db: Session = Depends(get_db)):
    """FR-3.B.5 / FR-5.4 - B2B exchange formats."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    return service.exchange_payload(db, pcf, format)


class ReviewIn(BaseModel):
    action: str            # peer_review | verify | certify
    reviewer: str
    certification_ref: str = ""
    notes: str = ""


@router.post("/pcf/{pcf_id}/review")
def review_pcf(pcf_id: int, payload: ReviewIn, db: Session = Depends(get_db),
               p: Principal = Depends(require("lca.verify"))):
    """FR-3.B.4 - peer review, verification and certification chain."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    now = datetime.now(timezone.utc)
    if payload.action == "peer_review":
        pcf.peer_reviewer = payload.reviewer
        pcf.peer_reviewed_at = now
        pcf.status = PCFStatus.PEER_REVIEWED
    elif payload.action == "verify":
        if pcf.status != PCFStatus.PEER_REVIEWED:
            raise HTTPException(409, "A PCF must be peer reviewed before verification")
        pcf.verifier = payload.reviewer
        pcf.verified_at = now
        pcf.status = PCFStatus.VERIFIED
    elif payload.action == "certify":
        if pcf.status != PCFStatus.VERIFIED:
            raise HTTPException(409, "A PCF must be verified before certification")
        pcf.certification_ref = payload.certification_ref or f"CERT-{pcf.id}-{now.year}"
        pcf.status = PCFStatus.CERTIFIED
    else:
        raise HTTPException(400, "action must be peer_review, verify or certify")
    db.commit()
    return to_dict(pcf, exclude={"lineage"})


@router.get("/pcf/{pcf_id}/certification-pack")
def certification_pack(pcf_id: int, db: Session = Depends(get_db)):
    """FR-3.B.4 - the evidence bundle handed to a verifier."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    prod = db.get(Product, pcf.product_id)
    evidence = db.scalars(select(Evidence).where(
        Evidence.object_type == "pcf", Evidence.object_id == pcf.id)).all()
    return {
        "pack_id": f"PCF-PACK-{pcf.id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product": to_dict(prod) if prod else {},
        "iso14067_report": service.iso14067_report(db, pcf),
        "source_evidence": rows(evidence),
        "evidence_count": len(evidence),
        "assumptions": pcf.assumptions,
        "uncertainty_pct": pcf.uncertainty_pct,
        "sensitivity_analysis": pcf.sensitivity,
        "review_chain": {
            "peer_reviewer": pcf.peer_reviewer,
            "peer_reviewed_at": pcf.peer_reviewed_at.isoformat() if pcf.peer_reviewed_at else None,
            "verifier": pcf.verifier,
            "verified_at": pcf.verified_at.isoformat() if pcf.verified_at else None,
            "certification_ref": pcf.certification_ref,
        },
        "exchange_formats": {
            "pact": service.exchange_payload(db, pcf, "pact"),
            "tfs": service.exchange_payload(db, pcf, "tfs"),
        },
    }


# ---------------------------------------------------------------------------
# FR-3.B.5  Eco-design, labels, declarations
# ---------------------------------------------------------------------------

class EcoDesignRequest(BaseModel):
    product_id: int
    boundary: str = LCABoundary.CRADLE_TO_GATE
    variants: list[dict] = Field(
        default_factory=list,
        description="Each variant: {name, material_substitutions:{bom_item_id: material_id}, "
                    "end_of_life_scenario}",
    )


@router.post("/eco-design/compare")
def eco_design_compare(payload: EcoDesignRequest, db: Session = Depends(get_db),
                       p: Principal = Depends(require("lca.read"))):
    """FR-3.B.1 / .5 - alternative-material scenarios and eco-design comparison."""
    prod = db.get(Product, payload.product_id)
    if prod is None:
        raise HTTPException(404, "Product not found")
    baseline = service.compute_pcf(db, prod, boundary=payload.boundary)
    results = [{
        "name": "Baseline (as designed)",
        "total_kgco2e": baseline["total_kgco2e"],
        "per_functional_unit_kgco2e": baseline["per_functional_unit_kgco2e"],
        "stage_breakdown": baseline["stage_breakdown"],
        "circularity_score": baseline["circularity_score"],
        "recycled_content_pct": baseline["recycled_content_pct"],
        "delta_kgco2e": 0.0, "delta_pct": 0.0, "is_baseline": True,
        "assumptions": baseline["assumptions"],
    }]
    for variant in payload.variants:
        subs = {int(k): int(v) for k, v in (variant.get("material_substitutions") or {}).items()}
        computed = service.compute_pcf(
            db, prod, boundary=payload.boundary,
            end_of_life_scenario=variant.get("end_of_life_scenario", "mixed"),
            material_substitutions=subs,
        )
        delta = computed["total_kgco2e"] - baseline["total_kgco2e"]
        results.append({
            "name": variant.get("name", "Variant"),
            "total_kgco2e": computed["total_kgco2e"],
            "per_functional_unit_kgco2e": computed["per_functional_unit_kgco2e"],
            "stage_breakdown": computed["stage_breakdown"],
            "circularity_score": computed["circularity_score"],
            "recycled_content_pct": computed["recycled_content_pct"],
            "delta_kgco2e": round(delta, 5),
            "delta_pct": round(delta / baseline["total_kgco2e"] * 100, 2)
            if baseline["total_kgco2e"] else 0.0,
            "is_baseline": False,
            "assumptions": computed["assumptions"],
        })
    results_sorted = sorted(results, key=lambda r: r["total_kgco2e"])
    return {
        "product": {"id": prod.id, "sku": prod.sku, "name": prod.name},
        "boundary": payload.boundary,
        "variants": results,
        "best_option": results_sorted[0]["name"],
        "max_reduction_kgco2e": round(
            baseline["total_kgco2e"] - results_sorted[0]["total_kgco2e"], 5),
    }


@router.get("/pcf/{pcf_id}/declaration")
def declaration(pcf_id: int, db: Session = Depends(get_db)):
    """FR-3.B.5 - environmental label, QR declaration and marketing-claim evidence."""
    pcf = db.get(PCF, pcf_id)
    if pcf is None:
        raise HTTPException(404, "PCF not found")
    prod = db.get(Product, pcf.product_id)
    verified = pcf.status in (PCFStatus.VERIFIED, PCFStatus.CERTIFIED)
    payload = {
        "sku": prod.sku if prod else "",
        "product": prod.name if prod else "",
        "kgco2e_per_unit": pcf.per_functional_unit_kgco2e,
        "boundary": pcf.boundary,
        "period": pcf.reference_period,
        "standard": "ISO 14067:2018",
        "status": pcf.status,
        "verifier": pcf.verifier,
        "pcf_id": pcf.id,
        "version": pcf.version,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    claim = (
        f"{pcf.per_functional_unit_kgco2e:.2f} kg CO2e per declared unit, "
        f"{pcf.boundary.replace('_', '-')}, {pcf.reference_period}"
    )
    return {
        "label": {
            "claim": claim,
            "substantiated": verified,
            "substantiation_note": (
                f"Independently verified by {pcf.verifier}."
                if verified else
                "NOT substantiated for external marketing use: the footprint has not been "
                "verified. Complete peer review and verification before publishing this claim."
            ),
            "recycled_content_pct": pcf.recycled_content_pct,
            "recyclability_pct": pcf.recyclability_pct,
        },
        "qr_payload": encoded,
        "qr_url": f"/declarations/{encoded}",
        "marketing_claim_evidence": {
            "pcf_id": pcf.id,
            "iso14067_ready": pcf.iso14067_ready,
            "review_status": pcf.status,
            "assumptions_count": len(pcf.assumptions or []),
            "uncertainty_pct": pcf.uncertainty_pct,
            "evidence_documents": rows(db.scalars(select(Evidence).where(
                Evidence.object_type == "pcf", Evidence.object_id == pcf.id))),
        },
    }


@router.get("/pcf/portfolio/summary")
def portfolio_summary(entity_id: int | None = None, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    """SKU-level footprint overview across the portfolio (FR-3.B.5)."""
    stmt = select(Product)
    if entity_id:
        stmt = stmt.where(Product.entity_id == entity_id)
    products = list(db.scalars(scoped(stmt, Product, p)))
    items, total_annual = [], 0.0
    for prod in products:
        pcf = db.scalars(
            select(PCF).where(PCF.product_id == prod.id, PCF.scenario_id.is_(None))
            .order_by(PCF.version.desc())
        ).first()
        if pcf is None:
            items.append({"sku": prod.sku, "name": prod.name, "status": "not_calculated"})
            continue
        annual = pcf.total_kgco2e * (prod.annual_volume or 0.0)
        total_annual += annual
        items.append({
            "product_id": prod.id, "sku": prod.sku, "name": prod.name,
            "category": prod.category,
            "kgco2e_per_unit": pcf.total_kgco2e,
            "annual_volume": prod.annual_volume,
            "annual_tco2e": round(annual / 1000, 3),
            "boundary": pcf.boundary, "status": pcf.status,
            "circularity_score": pcf.circularity_score,
            "iso14067_ready": pcf.iso14067_ready,
        })
    calculated = [i for i in items if i.get("status") != "not_calculated"]
    return {
        "product_count": len(products),
        "with_pcf": len(calculated),
        "coverage_pct": round(len(calculated) / len(products) * 100, 1) if products else 0.0,
        "verified_count": sum(1 for i in calculated
                              if i.get("status") in (PCFStatus.VERIFIED, PCFStatus.CERTIFIED)),
        "total_annual_tco2e": round(total_annual / 1000, 3),
        "products": sorted(items, key=lambda i: i.get("annual_tco2e", 0), reverse=True),
    }
