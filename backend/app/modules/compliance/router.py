"""4) Regulatory Compliance & Disclosure - FR-4.1 to FR-4.5."""
from __future__ import annotations

from datetime import date, datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import scoped
from app.core.serialize import page_response, rows, to_dict
from app.domain.enums import DisclosureStatus, FrameworkCode, Scope
from app.domain.models import (
    AssuranceRequest, Benchmark, CBAMDeclaration, CBAMGood, CDPResponse, Calculation,
    ClimateRisk, ClimateScenario, DataPoint, Disclosure, Emission, Entity, Evidence,
    Framework, InternalCarbonPrice, MaterialityAssessment, Product, Supplier, Target,
    TaxonomyActivity, TransitionPlan,
)
from app.engine import lineage

router = APIRouter(prefix="/compliance", tags=["4) Regulatory Compliance & Disclosure"])

# ESRS E1 climate data points the platform can populate from the ledger.
ESRS_E1_DATAPOINTS = [
    ("E1-1", "Transition plan for climate change mitigation", "", "text"),
    ("E1-2", "Policies related to climate change mitigation and adaptation", "", "text"),
    ("E1-3", "Actions and resources in relation to climate change policies", "", "text"),
    ("E1-4", "Targets related to climate change mitigation and adaptation", "tCO2e", "number"),
    ("E1-5", "Energy consumption and mix", "MWh", "number"),
    ("E1-6-1", "Gross Scope 1 GHG emissions", "tCO2e", "number"),
    ("E1-6-2", "Gross Scope 2 GHG emissions (location-based)", "tCO2e", "number"),
    ("E1-6-3", "Gross Scope 2 GHG emissions (market-based)", "tCO2e", "number"),
    ("E1-6-4", "Gross Scope 3 GHG emissions", "tCO2e", "number"),
    ("E1-6-5", "Total GHG emissions", "tCO2e", "number"),
    ("E1-7", "GHG removals and mitigation projects financed through carbon credits", "tCO2e", "number"),
    ("E1-8", "Internal carbon pricing", "EUR/tCO2e", "number"),
    ("E1-9", "Anticipated financial effects from material physical and transition risks", "EUR", "number"),
]

TCFD_PILLARS = ["governance", "strategy", "risk_management", "metrics_and_targets"]

DNSH_OBJECTIVES = [
    "climate_mitigation", "climate_adaptation", "water_and_marine",
    "circular_economy", "pollution_prevention", "biodiversity",
]


# ---------------------------------------------------------------------------
# Frameworks & disclosures (shared spine for FR-4.1 - .5)
# ---------------------------------------------------------------------------

@router.get("/frameworks")
def list_frameworks(db: Session = Depends(get_db)):
    return rows(db.scalars(select(Framework).order_by(Framework.code)))


@router.get("/disclosures")
def list_disclosures(framework_code: str | None = None, entity_id: int | None = None,
                     year: int | None = None, page: int = 1, page_size: int = 50,
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Disclosure).order_by(Disclosure.reporting_year.desc())
    if framework_code:
        fw = db.scalars(select(Framework).where(Framework.code == framework_code)).first()
        stmt = stmt.where(Disclosure.framework_id == (fw.id if fw else -1))
    if entity_id:
        stmt = stmt.where(Disclosure.entity_id == entity_id)
    if year:
        stmt = stmt.where(Disclosure.reporting_year == year)

    def mapper(d: Disclosure) -> dict:
        fw = db.get(Framework, d.framework_id)
        ent = db.get(Entity, d.entity_id)
        points = db.scalars(select(DataPoint).where(DataPoint.disclosure_id == d.id)).all()
        verified = sum(1 for dp in points if dp.verification_status == "verified")
        return to_dict(d, exclude={"xbrl_document"}, extra={
            "framework_code": fw.code if fw else None,
            "framework_name": fw.name if fw else None,
            "entity_name": ent.name if ent else None,
            "data_point_count": len(points),
            "verified_count": verified,
            "verification_pct": round(verified / len(points) * 100, 1) if points else 0.0,
        })

    return page_response(db, scoped(stmt, Disclosure, p), page=page,
                         page_size=page_size, mapper=mapper)


@router.get("/disclosures/{disclosure_id}")
def get_disclosure(disclosure_id: int, db: Session = Depends(get_db)):
    d = db.get(Disclosure, disclosure_id)
    if d is None:
        raise HTTPException(404, "Disclosure not found")
    fw = db.get(Framework, d.framework_id)
    ent = db.get(Entity, d.entity_id)
    points = db.scalars(select(DataPoint).where(DataPoint.disclosure_id == d.id)
                        .order_by(DataPoint.code)).all()
    return to_dict(d, extra={
        "framework": to_dict(fw) if fw else None,
        "entity_name": ent.name if ent else None,
        "data_points": rows(points),
        "assurance_requests": rows(db.scalars(select(AssuranceRequest)
                                              .where(AssuranceRequest.disclosure_id == d.id))),
    })


def _scope_totals(db: Session, entity_id: int, year: int) -> dict:
    def total(scope: str, method: str | None = None) -> float:
        stmt = select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.entity_id == entity_id, Emission.year == year,
            Emission.scope == scope, Emission.scenario_id.is_(None))
        if method:
            stmt = stmt.where(Emission.scope2_method == method)
        return float(db.scalar(stmt) or 0.0) / 1000

    s2_market = total(Scope.SCOPE_2, "market_based")
    s2_location = total(Scope.SCOPE_2) - s2_market
    return {
        "scope_1": round(total(Scope.SCOPE_1), 3),
        "scope_2_location": round(s2_location, 3),
        "scope_2_market": round(s2_market, 3),
        "scope_3": round(total(Scope.SCOPE_3), 3),
        "total": round(total(Scope.SCOPE_1) + s2_location + total(Scope.SCOPE_3), 3),
    }


def _source_calculation_ids(db: Session, entity_id: int, year: int,
                            scope: str | None = None) -> list[int]:
    stmt = select(Emission.calculation_id).where(
        Emission.entity_id == entity_id, Emission.year == year,
        Emission.scenario_id.is_(None))
    if scope:
        stmt = stmt.where(Emission.scope == scope)
    return [int(i) for i in db.scalars(stmt)][:500]


# ---------------------------------------------------------------------------
# FR-4.1  CSRD / ESRS
# ---------------------------------------------------------------------------

class CSRDBuildIn(BaseModel):
    entity_id: int
    reporting_year: int = date.today().year
    consolidate_subsidiaries: bool = True


@router.post("/csrd/disclosures/build")
def build_csrd(payload: CSRDBuildIn, db: Session = Depends(get_db),
               p: Principal = Depends(require("compliance.write"))):
    """FR-4.1 - entity consolidation, data-point verification and XBRL mapping."""
    fw = db.scalars(select(Framework).where(Framework.code == FrameworkCode.CSRD_ESRS)).first()
    if fw is None:
        raise HTTPException(404, "CSRD/ESRS framework not configured")
    entity = db.get(Entity, payload.entity_id)
    if entity is None:
        raise HTTPException(404, "Entity not found")

    disclosure = db.scalars(select(Disclosure).where(
        Disclosure.framework_id == fw.id, Disclosure.entity_id == payload.entity_id,
        Disclosure.reporting_year == payload.reporting_year)).first()
    if disclosure is None:
        disclosure = Disclosure(framework_id=fw.id, entity_id=payload.entity_id,
                                reporting_year=payload.reporting_year,
                                title=f"CSRD/ESRS {payload.reporting_year} - {entity.name}")
        db.add(disclosure)
        db.flush()

    totals = _scope_totals(db, payload.entity_id, payload.reporting_year)
    material_topics = {
        m.topic_code for m in db.scalars(select(MaterialityAssessment).where(
            MaterialityAssessment.entity_id == payload.entity_id,
            MaterialityAssessment.reporting_year == payload.reporting_year,
            MaterialityAssessment.is_material.is_(True)))
    }
    plan = db.scalars(select(TransitionPlan)
                      .where(TransitionPlan.entity_id == payload.entity_id)).first()

    values = {
        "E1-6-1": totals["scope_1"], "E1-6-2": totals["scope_2_location"],
        "E1-6-3": totals["scope_2_market"], "E1-6-4": totals["scope_3"],
        "E1-6-5": totals["total"],
    }
    existing = {dp.code: dp for dp in db.scalars(
        select(DataPoint).where(DataPoint.disclosure_id == disclosure.id))}

    created = 0
    for code, label, unit, kind in ESRS_E1_DATAPOINTS:
        dp = existing.get(code)
        if dp is None:
            dp = DataPoint(disclosure_id=disclosure.id, code=code, label=label, unit=unit)
            db.add(dp)
            created += 1
        dp.label, dp.unit = label, unit
        dp.xbrl_tag = f"esrs:{code.replace('-', '')}"
        if code in values:
            dp.value_numeric = values[code]
            scope_map = {"E1-6-1": Scope.SCOPE_1, "E1-6-2": Scope.SCOPE_2,
                         "E1-6-3": Scope.SCOPE_2, "E1-6-4": Scope.SCOPE_3}
            dp.source_calculation_ids = _source_calculation_ids(
                db, payload.entity_id, payload.reporting_year, scope_map.get(code))
            dp.verification_status = "verified" if dp.source_calculation_ids else "unverified"
        elif code == "E1-1" and plan:
            dp.value_text = plan.narrative or plan.name
            dp.verification_status = "verified"
        dp.is_material = code.startswith("E1") and (not material_topics or "E1" in material_topics)
        dp.evidence_count = db.scalar(
            select(func.count()).select_from(Evidence).where(
                Evidence.object_type == "data_point", Evidence.object_id == dp.id)) or 0

    db.flush()
    points = list(db.scalars(select(DataPoint).where(DataPoint.disclosure_id == disclosure.id)))
    populated = sum(1 for dp in points
                    if dp.value_numeric is not None or dp.value_text)
    disclosure.completeness_pct = round(populated / len(points) * 100, 1) if points else 0.0
    disclosure.assurance_ready = disclosure.completeness_pct >= 90
    db.commit()
    return {
        "disclosure_id": disclosure.id,
        "data_points_created": created,
        "data_point_count": len(points),
        "completeness_pct": disclosure.completeness_pct,
        "assurance_ready": disclosure.assurance_ready,
        "totals": totals,
        "material_topics": sorted(material_topics),
    }


@router.get("/csrd/double-materiality")
def double_materiality(entity_id: int, reporting_year: int = Query(default=date.today().year),
                       db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.1 - impact (inside-out) and financial (outside-in) materiality."""
    rows_ = list(db.scalars(select(MaterialityAssessment).where(
        MaterialityAssessment.entity_id == entity_id,
        MaterialityAssessment.reporting_year == reporting_year)))
    return {
        "entity_id": entity_id, "reporting_year": reporting_year,
        "matrix": [
            {**to_dict(m),
             "quadrant": ("double_material" if m.impact_score >= 3 and m.financial_score >= 3
                          else "impact_material" if m.impact_score >= 3
                          else "financially_material" if m.financial_score >= 3
                          else "not_material")}
            for m in rows_
        ],
        "material_count": sum(1 for m in rows_ if m.is_material),
        "value_chain_coverage": sorted({m.value_chain_stage for m in rows_}),
    }


class MaterialityIn(BaseModel):
    entity_id: int
    reporting_year: int
    topic_code: str
    topic: str
    impact_score: float
    financial_score: float
    value_chain_stage: str = "own_operations"
    rationale: str = ""
    stakeholders_consulted: list[str] = Field(default_factory=list)


@router.post("/csrd/double-materiality", status_code=201)
def upsert_materiality(payload: MaterialityIn, db: Session = Depends(get_db),
                       p: Principal = Depends(require("compliance.write"))):
    row = db.scalars(select(MaterialityAssessment).where(
        MaterialityAssessment.entity_id == payload.entity_id,
        MaterialityAssessment.reporting_year == payload.reporting_year,
        MaterialityAssessment.topic_code == payload.topic_code)).first()
    if row is None:
        row = MaterialityAssessment(**payload.model_dump())
        db.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
    row.is_material = row.impact_score >= 3 or row.financial_score >= 3
    db.commit()
    return to_dict(row)


@router.get("/csrd/value-chain")
def value_chain_disclosure(entity_id: int, reporting_year: int = Query(default=date.today().year),
                           db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.1 - value-chain disclosures (upstream, own operations, downstream)."""
    totals = _scope_totals(db, entity_id, reporting_year)
    upstream_categories = list(range(1, 9))
    downstream_categories = list(range(9, 16))
    ups, downs = 0.0, 0.0
    for e in db.scalars(select(Emission).where(
            Emission.entity_id == entity_id, Emission.year == reporting_year,
            Emission.scope == Scope.SCOPE_3, Emission.scenario_id.is_(None))):
        cat = db.get(Category, e.category_id) if e.category_id else None
        if cat and cat.number in downstream_categories:
            downs += e.co2e_kg
        else:
            ups += e.co2e_kg
    suppliers_engaged = db.scalar(select(func.count()).select_from(Supplier).where(
        Supplier.onboarding_status == "responded")) or 0
    suppliers_total = db.scalar(select(func.count()).select_from(Supplier)) or 0
    return {
        "entity_id": entity_id, "reporting_year": reporting_year,
        "upstream_tco2e": round(ups / 1000, 3),
        "own_operations_tco2e": round(totals["scope_1"] + totals["scope_2_location"], 3),
        "downstream_tco2e": round(downs / 1000, 3),
        "total_tco2e": totals["total"],
        "upstream_categories": upstream_categories,
        "downstream_categories": downstream_categories,
        "primary_data_coverage_pct": round(
            suppliers_engaged / suppliers_total * 100, 1) if suppliers_total else 0.0,
        "suppliers_engaged": suppliers_engaged, "suppliers_total": suppliers_total,
    }


@router.get("/csrd/transition-plan")
def transition_plan(entity_id: int, db: Session = Depends(get_db),
                    p: Principal = Depends(get_principal)):
    plans = rows(db.scalars(select(TransitionPlan)
                            .where(TransitionPlan.entity_id == entity_id)))
    return {"entity_id": entity_id, "plans": plans}


@router.get("/csrd/disclosures/{disclosure_id}/xbrl")
def xbrl_export(disclosure_id: int, db: Session = Depends(get_db)):
    """FR-4.1 - XBRL mapping and inline document generation."""
    d = db.get(Disclosure, disclosure_id)
    if d is None:
        raise HTTPException(404, "Disclosure not found")
    entity = db.get(Entity, d.entity_id)
    points = db.scalars(select(DataPoint).where(DataPoint.disclosure_id == d.id)
                        .order_by(DataPoint.code)).all()
    context_id = f"ctx_{d.reporting_year}"
    facts = []
    for dp in points:
        if dp.value_numeric is None and not dp.value_text:
            continue
        if dp.value_numeric is not None:
            facts.append(
                f'  <{dp.xbrl_tag} contextRef="{context_id}" unitRef="tCO2e" decimals="2">'
                f"{dp.value_numeric}</{dp.xbrl_tag}>")
        else:
            facts.append(f'  <{dp.xbrl_tag} contextRef="{context_id}">'
                         f"{escape(dp.value_text[:2000])}</{dp.xbrl_tag}>")
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:esrs="https://xbrl.efrag.org/taxonomy/esrs">\n'
        f'  <context id="{context_id}">\n'
        f"    <entity><identifier scheme=\"urn:decarbx\">{escape(entity.code if entity else '')}"
        "</identifier></entity>\n"
        f"    <period><startDate>{d.reporting_year}-01-01</startDate>"
        f"<endDate>{d.reporting_year}-12-31</endDate></period>\n"
        "  </context>\n"
        '  <unit id="tCO2e"><measure>esrs:tCO2e</measure></unit>\n'
        + "\n".join(facts) + "\n</xbrl>"
    )
    d.xbrl_document = document
    db.commit()
    return {
        "disclosure_id": d.id, "reporting_year": d.reporting_year,
        "fact_count": len(facts),
        "mapping": [{"code": dp.code, "label": dp.label, "xbrl_tag": dp.xbrl_tag,
                     "unit": dp.unit, "value": dp.value_numeric if dp.value_numeric is not None
                     else dp.value_text,
                     "verification_status": dp.verification_status}
                    for dp in points],
        "document": document,
    }


@router.get("/data-points/{data_point_id}/verify")
def verify_data_point(data_point_id: int, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    """FR-4.1 data-point verification, resolved through FR-7.2 lineage."""
    dp = db.get(DataPoint, data_point_id)
    if dp is None:
        raise HTTPException(404, "Data point not found")
    traces = []
    for cid in (dp.source_calculation_ids or [])[:25]:
        try:
            trace = lineage.read(db, cid)
            traces.append({"calculation_id": cid,
                           "co2e_kg": trace.get("calculation", {}).get("co2e_kg"),
                           "status": trace.get("calculation", {}).get("status"),
                           "audit_grade": trace.get("completeness", {}).get("is_audit_grade"),
                           "factor": trace.get("emission_factor", {}).get("name"),
                           "method": trace.get("method", {})})
        except LookupError:
            continue
    return {
        "data_point": to_dict(dp),
        "source_calculation_count": len(dp.source_calculation_ids or []),
        "traces_sampled": traces,
        "all_audit_grade": all(t["audit_grade"] for t in traces) if traces else False,
        "evidence": rows(db.scalars(select(Evidence).where(
            Evidence.object_type == "data_point", Evidence.object_id == dp.id))),
    }


@router.post("/disclosures/{disclosure_id}/approve")
def approve_disclosure(disclosure_id: int, comment: str = Body(default="", embed=True),
                       db: Session = Depends(get_db),
                       p: Principal = Depends(require("compliance.file"))):
    d = db.get(Disclosure, disclosure_id)
    if d is None:
        raise HTTPException(404, "Disclosure not found")
    d.status = DisclosureStatus.APPROVED
    d.approved_by_id = p.user.id
    d.approved_at = datetime.now(timezone.utc)
    lineage.record_change(db, action="approve", object_type="disclosure",
                          object_id=d.id, user_id=p.user.id, user_email=p.user.email,
                          after={"status": d.status}, reason=comment)
    db.commit()
    return to_dict(d, exclude={"xbrl_document"})


# ---------------------------------------------------------------------------
# FR-4.2  CBAM
# ---------------------------------------------------------------------------

@router.get("/cbam/declarations")
def list_cbam(entity_id: int | None = None, year: int | None = None,
              db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(CBAMDeclaration).order_by(CBAMDeclaration.reporting_year.desc(),
                                            CBAMDeclaration.quarter.desc())
    if entity_id:
        stmt = stmt.where(CBAMDeclaration.entity_id == entity_id)
    if year:
        stmt = stmt.where(CBAMDeclaration.reporting_year == year)
    out = []
    for d in db.scalars(scoped(stmt, CBAMDeclaration, p)):
        goods = db.scalars(select(CBAMGood).where(CBAMGood.declaration_id == d.id)).all()
        out.append({**to_dict(d), "goods_count": len(goods),
                    "actual_data_pct": round(
                        sum(1 for g in goods if g.data_basis == "actual") / len(goods) * 100, 1)
                    if goods else 0.0})
    return out


@router.get("/cbam/declarations/{declaration_id}")
def get_cbam(declaration_id: int, db: Session = Depends(get_db)):
    d = db.get(CBAMDeclaration, declaration_id)
    if d is None:
        raise HTTPException(404, "CBAM declaration not found")
    goods = db.scalars(select(CBAMGood).where(CBAMGood.declaration_id == d.id)).all()

    def good_row(g: CBAMGood) -> dict:
        supplier = db.get(Supplier, g.supplier_id) if g.supplier_id else None
        product = db.get(Product, g.product_id) if g.product_id else None
        embedded = (g.direct_embedded_tco2e_per_t + g.indirect_embedded_tco2e_per_t) \
            * g.quantity_tonnes
        return to_dict(g, extra={
            "supplier_name": supplier.name if supplier else None,
            "product_sku": product.sku if product else None,
            "total_embedded_tco2e": round(embedded, 3),
            "evidence": to_dict(db.get(Evidence, g.evidence_id)) if g.evidence_id else None,
        })

    return {**to_dict(d), "goods": [good_row(g) for g in goods]}


class CBAMBuildIn(BaseModel):
    entity_id: int
    reporting_year: int = date.today().year
    quarter: int = 1
    certificate_price: float = 80.0


@router.post("/cbam/declarations/compute")
def compute_cbam(payload: CBAMBuildIn, db: Session = Depends(get_db),
                 p: Principal = Depends(require("compliance.write"))):
    """FR-4.2 - embedded emissions, certificates, payments and adjustments."""
    d = db.scalars(select(CBAMDeclaration).where(
        CBAMDeclaration.entity_id == payload.entity_id,
        CBAMDeclaration.reporting_year == payload.reporting_year,
        CBAMDeclaration.quarter == payload.quarter)).first()
    if d is None:
        d = CBAMDeclaration(entity_id=payload.entity_id,
                            reporting_year=payload.reporting_year,
                            quarter=payload.quarter)
        db.add(d)
        db.flush()

    goods = list(db.scalars(select(CBAMGood).where(CBAMGood.declaration_id == d.id)))
    total = sum((g.direct_embedded_tco2e_per_t + g.indirect_embedded_tco2e_per_t)
                * g.quantity_tonnes for g in goods)
    carbon_price_paid = sum(g.carbon_price_paid for g in goods)

    d.total_embedded_tco2e = round(total, 3)
    d.certificate_price = payload.certificate_price
    d.certificates_required = round(total, 3)
    gross = total * payload.certificate_price
    d.payment_due = round(max(0.0, gross - carbon_price_paid), 2)
    d.adjustments = [{
        "type": "carbon_price_paid_in_origin",
        "amount": round(carbon_price_paid, 2),
        "note": "Deduction for carbon price already paid in the country of origin.",
    }] if carbon_price_paid else []
    d.status = "computed"
    db.commit()
    return {
        **to_dict(d),
        "goods_count": len(goods),
        "default_data_lines": sum(1 for g in goods if g.data_basis == "default"),
        "actual_data_lines": sum(1 for g in goods if g.data_basis == "actual"),
        "gross_liability": round(gross, 2),
        "evidence_complete": all(g.evidence_id for g in goods) if goods else False,
    }


@router.post("/cbam/goods/{good_id}/request-supplier-data")
def request_cbam_supplier_data(good_id: int, db: Session = Depends(get_db),
                               p: Principal = Depends(require("compliance.write"))):
    """FR-4.2 - supplier requests for actual embedded emissions."""
    g = db.get(CBAMGood, good_id)
    if g is None:
        raise HTTPException(404, "CBAM good not found")
    g.supplier_request_status = "requested"
    supplier = db.get(Supplier, g.supplier_id) if g.supplier_id else None
    db.commit()
    return {"good_id": g.id, "cn_code": g.cn_code,
            "supplier": supplier.name if supplier else None,
            "status": g.supplier_request_status,
            "message": "Actual embedded-emissions data requested from the supplier. "
                       "Until it arrives the declaration uses default values."}


# ---------------------------------------------------------------------------
# FR-4.3  TCFD & climate risk
# ---------------------------------------------------------------------------

@router.get("/tcfd/report")
def tcfd_report(entity_id: int, reporting_year: int = Query(default=date.today().year),
                db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.3 - the four pillars with metrics, targets, controls and documentation."""
    entity = db.get(Entity, entity_id)
    risks = list(db.scalars(select(ClimateRisk).where(ClimateRisk.entity_id == entity_id)))
    scenarios = list(db.scalars(select(ClimateScenario)
                                .where(ClimateScenario.entity_id == entity_id)))
    totals = _scope_totals(db, entity_id, reporting_year)
    targets = rows(db.scalars(select(Target).where(Target.entity_id == entity_id)))
    price_row = db.scalars(select(InternalCarbonPrice)
                           .where(InternalCarbonPrice.is_active.is_(True))).first()
    return {
        "entity_id": entity_id, "entity_name": entity.name if entity else None,
        "reporting_year": reporting_year,
        "pillars": TCFD_PILLARS,
        "governance": {
            "board_oversight": "Board Sustainability Committee reviews climate risk quarterly.",
            "management_role": "Chief Sustainability Officer owns the climate risk register.",
            "risk_owners": sorted({r.governance_owner for r in risks if r.governance_owner}),
            "documented": bool(risks),
        },
        "strategy": {
            "risks": [to_dict(r) for r in risks if not r.is_opportunity],
            "opportunities": [to_dict(r) for r in risks if r.is_opportunity],
            "scenarios": [to_dict(s) for s in scenarios],
            "financial_impact_total": {
                "low": round(sum(r.financial_impact_low for r in risks
                                 if not r.is_opportunity), 2),
                "high": round(sum(r.financial_impact_high for r in risks
                                  if not r.is_opportunity), 2),
            },
            "horizons": sorted({r.horizon for r in risks}),
        },
        "risk_management": {
            "identification_process": "Annual bottom-up register per entity, reviewed centrally.",
            "controls": [{"risk": r.title, "control": r.control, "mitigation": r.mitigation}
                         for r in risks if r.control or r.mitigation],
            "controls_documented_pct": round(
                sum(1 for r in risks if r.control) / len(risks) * 100, 1) if risks else 0.0,
        },
        "metrics_and_targets": {
            "emissions": totals,
            "targets": targets,
            "internal_carbon_price": (price_row.price_per_tonne if price_row else None),
        },
        "disclosure_completeness_pct": round(
            (bool(risks) * 25 + bool(scenarios) * 25 + bool(targets) * 25
             + (totals["total"] > 0) * 25), 1),
    }


class RiskIn(BaseModel):
    entity_id: int
    title: str
    risk_type: str
    is_opportunity: bool = False
    horizon: str = "medium"
    likelihood: str = "possible"
    impact_rating: str = "moderate"
    financial_impact_low: float = 0.0
    financial_impact_high: float = 0.0
    scenario_ref: str = ""
    mitigation: str = ""
    control: str = ""
    governance_owner: str = ""


@router.post("/tcfd/risks", status_code=201)
def create_risk(payload: RiskIn, db: Session = Depends(get_db),
                p: Principal = Depends(require("compliance.write"))):
    r = ClimateRisk(**payload.model_dump())
    db.add(r)
    db.commit()
    return to_dict(r)


@router.get("/tcfd/scenarios")
def list_climate_scenarios(entity_id: int | None = None, db: Session = Depends(get_db),
                           p: Principal = Depends(get_principal)):
    stmt = select(ClimateScenario)
    if entity_id:
        stmt = stmt.where(ClimateScenario.entity_id == entity_id)
    return rows(db.scalars(scoped(stmt, ClimateScenario, p)))


# ---------------------------------------------------------------------------
# FR-4.4  EU Taxonomy
# ---------------------------------------------------------------------------

@router.get("/taxonomy/activities")
def list_taxonomy(entity_id: int | None = None,
                  reporting_year: int = Query(default=date.today().year),
                  db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(TaxonomyActivity).where(TaxonomyActivity.reporting_year == reporting_year)
    if entity_id:
        stmt = stmt.where(TaxonomyActivity.entity_id == entity_id)
    return rows(db.scalars(scoped(stmt, TaxonomyActivity, p)))


class TaxonomyIn(BaseModel):
    entity_id: int
    reporting_year: int
    activity_code: str
    activity_name: str
    objective: str = "climate_mitigation"
    is_eligible: bool = False
    substantial_contribution_met: bool = False
    technical_criteria: dict = Field(default_factory=dict)
    dnsh_checks: dict = Field(default_factory=dict)
    minimum_safeguards_met: bool = False
    revenue_amount: float = 0.0
    capex_amount: float = 0.0
    opex_amount: float = 0.0


@router.post("/taxonomy/activities", status_code=201)
def upsert_taxonomy(payload: TaxonomyIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("compliance.write"))):
    """FR-4.4 - eligibility/alignment with technical criteria, DNSH and safeguards."""
    row = db.scalars(select(TaxonomyActivity).where(
        TaxonomyActivity.entity_id == payload.entity_id,
        TaxonomyActivity.reporting_year == payload.reporting_year,
        TaxonomyActivity.activity_code == payload.activity_code)).first()
    if row is None:
        row = TaxonomyActivity(**payload.model_dump())
        db.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
    # Alignment requires all three legs: substantial contribution, DNSH, safeguards.
    dnsh_ok = all(row.dnsh_checks.get(o, False) for o in DNSH_OBJECTIVES
                  if o != row.objective) if row.dnsh_checks else False
    row.is_aligned = bool(row.is_eligible and row.substantial_contribution_met
                          and dnsh_ok and row.minimum_safeguards_met)
    db.commit()
    return {**to_dict(row), "dnsh_all_passed": dnsh_ok,
            "dnsh_objectives_required": [o for o in DNSH_OBJECTIVES if o != row.objective]}


@router.get("/taxonomy/kpis")
def taxonomy_kpis(entity_id: int, reporting_year: int = Query(default=date.today().year),
                  db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.4 - CapEx/OpEx/revenue allocation and reporting."""
    activities = list(db.scalars(select(TaxonomyActivity).where(
        TaxonomyActivity.entity_id == entity_id,
        TaxonomyActivity.reporting_year == reporting_year)))
    entity = db.get(Entity, entity_id)
    total_revenue = entity.revenue if entity and entity.revenue else \
        sum(a.revenue_amount for a in activities) or 1.0
    total_capex = sum(a.capex_amount for a in activities) or 1.0
    total_opex = sum(a.opex_amount for a in activities) or 1.0

    def share(items, attr, denominator):
        return round(sum(getattr(a, attr) for a in items) / denominator * 100, 2)

    eligible = [a for a in activities if a.is_eligible]
    aligned = [a for a in activities if a.is_aligned]
    for a in activities:
        a.revenue_share_pct = round(a.revenue_amount / total_revenue * 100, 3)
        a.capex_share_pct = round(a.capex_amount / total_capex * 100, 3)
        a.opex_share_pct = round(a.opex_amount / total_opex * 100, 3)
    db.commit()
    return {
        "entity_id": entity_id, "reporting_year": reporting_year,
        "activity_count": len(activities),
        "eligible_count": len(eligible), "aligned_count": len(aligned),
        "kpis": {
            "revenue": {"eligible_pct": share(eligible, "revenue_amount", total_revenue),
                        "aligned_pct": share(aligned, "revenue_amount", total_revenue),
                        "total": total_revenue},
            "capex": {"eligible_pct": share(eligible, "capex_amount", total_capex),
                      "aligned_pct": share(aligned, "capex_amount", total_capex),
                      "total": total_capex},
            "opex": {"eligible_pct": share(eligible, "opex_amount", total_opex),
                     "aligned_pct": share(aligned, "opex_amount", total_opex),
                     "total": total_opex},
        },
        "activities": rows(activities),
        "dnsh_objectives": DNSH_OBJECTIVES,
    }


# ---------------------------------------------------------------------------
# FR-4.5  SEC climate & CDP
# ---------------------------------------------------------------------------

@router.get("/sec/disclosure")
def sec_disclosure(entity_id: int, reporting_year: int = Query(default=date.today().year),
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.5 - Scope disclosures, attestation evidence and materiality."""
    totals = _scope_totals(db, entity_id, reporting_year)
    entity = db.get(Entity, entity_id)
    material = list(db.scalars(select(MaterialityAssessment).where(
        MaterialityAssessment.entity_id == entity_id,
        MaterialityAssessment.reporting_year == reporting_year,
        MaterialityAssessment.is_material.is_(True))))
    assurance = list(db.scalars(select(AssuranceRequest)
                                .where(AssuranceRequest.entity_id == entity_id)))
    evidence_count = db.scalar(select(func.count()).select_from(Evidence)) or 0
    return {
        "entity_id": entity_id, "entity_name": entity.name if entity else None,
        "reporting_year": reporting_year,
        "scope_disclosures": {
            "scope_1_tco2e": totals["scope_1"],
            "scope_2_location_tco2e": totals["scope_2_location"],
            "scope_2_market_tco2e": totals["scope_2_market"],
            "scope_3_tco2e": totals["scope_3"],
            "scope_3_disclosed": totals["scope_3"] > 0,
        },
        "materiality": {
            "material_topics": [m.topic for m in material],
            "assessment_count": len(material),
        },
        "attestation": {
            "requests": rows(assurance),
            "highest_level": max((a.assurance_level for a in assurance), default="none"),
            "completed": sum(1 for a in assurance if a.status == "completed"),
        },
        "evidence_library_size": evidence_count,
        "readiness_pct": round(
            (bool(totals["scope_1"]) * 30 + bool(totals["scope_2_location"]) * 30
             + bool(material) * 20 + bool(assurance) * 20), 1),
    }


@router.get("/cdp/responses")
def cdp_responses(entity_id: int, reporting_year: int = Query(default=date.today().year),
                  db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.5 - questionnaires, review workflow, benchmarks and response history."""
    responses = list(db.scalars(select(CDPResponse).where(
        CDPResponse.entity_id == entity_id,
        CDPResponse.reporting_year == reporting_year).order_by(CDPResponse.question_code)))
    history = db.execute(
        select(CDPResponse.reporting_year, func.count(CDPResponse.id))
        .where(CDPResponse.entity_id == entity_id)
        .group_by(CDPResponse.reporting_year).order_by(CDPResponse.reporting_year)
    ).all()
    benchmarks = rows(db.scalars(select(Benchmark)
                                 .where(Benchmark.year == reporting_year)))
    answered = sum(1 for r in responses if r.answer)
    return {
        "entity_id": entity_id, "reporting_year": reporting_year,
        "question_count": len(responses),
        "answered": answered,
        "completeness_pct": round(answered / len(responses) * 100, 1) if responses else 0.0,
        "by_module": sorted({r.module for r in responses}),
        "responses": rows(responses),
        "response_history": [{"year": int(r[0]), "question_count": int(r[1])} for r in history],
        "peer_benchmarks": benchmarks,
        "review_workflow": {
            "draft": sum(1 for r in responses if r.status == "draft"),
            "in_review": sum(1 for r in responses if r.status == "in_review"),
            "approved": sum(1 for r in responses if r.status == "approved"),
        },
    }


@router.put("/cdp/responses/{response_id}")
def update_cdp(response_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
               p: Principal = Depends(require("compliance.write"))):
    r = db.get(CDPResponse, response_id)
    if r is None:
        raise HTTPException(404, "CDP response not found")
    for k, v in payload.items():
        if hasattr(r, k) and k != "id":
            setattr(r, k, v)
    db.commit()
    return to_dict(r)


# ---------------------------------------------------------------------------
# Assurance (FR-4.1 / FR-4.5)
# ---------------------------------------------------------------------------

class AssuranceIn(BaseModel):
    entity_id: int
    disclosure_id: int | None = None
    pcf_id: int | None = None
    assurer: str
    assurance_level: str = "limited"
    scope_description: str = ""
    due_date: date | None = None


@router.post("/assurance-requests", status_code=201)
def create_assurance(payload: AssuranceIn, db: Session = Depends(get_db),
                     p: Principal = Depends(require("compliance.write"))):
    a = AssuranceRequest(**payload.model_dump(),
                         evidence_pack_ref=f"PACK-{payload.entity_id}-{date.today().year}")
    db.add(a)
    db.commit()
    return to_dict(a)


@router.get("/assurance-requests")
def list_assurance(entity_id: int | None = None, status: str | None = None,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(AssuranceRequest).order_by(AssuranceRequest.requested_at.desc())
    if entity_id:
        stmt = stmt.where(AssuranceRequest.entity_id == entity_id)
    if status:
        stmt = stmt.where(AssuranceRequest.status == status)
    return rows(db.scalars(scoped(stmt, AssuranceRequest, p)))


@router.post("/assurance-requests/{request_id}/decide")
def decide_assurance(request_id: int, status: str = Body(...),
                     findings: list[dict] = Body(default=[]),
                     db: Session = Depends(get_db),
                     p: Principal = Depends(require("assurance.decide"))):
    a = db.get(AssuranceRequest, request_id)
    if a is None:
        raise HTTPException(404, "Assurance request not found")
    a.status = status
    a.findings = findings
    if status == "completed":
        a.completed_at = datetime.now(timezone.utc)
        if a.disclosure_id:
            d = db.get(Disclosure, a.disclosure_id)
            if d:
                d.status = DisclosureStatus.ASSURED
    db.commit()
    return to_dict(a)


@router.get("/evidence")
def evidence_library(object_type: str | None = None, status: str | None = None,
                     q: str | None = None, page: int = 1, page_size: int = 50,
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-4.5 - the evidence library, shared across every framework."""
    stmt = select(Evidence).order_by(Evidence.created_at.desc())
    if object_type:
        stmt = stmt.where(Evidence.object_type == object_type)
    if status:
        stmt = stmt.where(Evidence.status == status)
    if q:
        stmt = stmt.where(Evidence.title.like(f"%{q}%"))
    return page_response(db, scoped(stmt, Evidence, p), page=page, page_size=page_size)


@router.get("/readiness")
def compliance_readiness(entity_id: int, reporting_year: int = Query(default=date.today().year),
                         db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """One view of where every framework stands for this entity and year."""
    frameworks = list(db.scalars(select(Framework)))
    out = []
    for fw in frameworks:
        d = db.scalars(select(Disclosure).where(
            Disclosure.framework_id == fw.id, Disclosure.entity_id == entity_id,
            Disclosure.reporting_year == reporting_year)).first()
        if fw.code == FrameworkCode.CBAM:
            declarations = list(db.scalars(select(CBAMDeclaration).where(
                CBAMDeclaration.entity_id == entity_id,
                CBAMDeclaration.reporting_year == reporting_year)))
            completeness = round(len(declarations) / 4 * 100, 1)
            status = "filed" if len(declarations) >= 4 else "draft"
        elif fw.code == FrameworkCode.EU_TAXONOMY:
            acts = list(db.scalars(select(TaxonomyActivity).where(
                TaxonomyActivity.entity_id == entity_id,
                TaxonomyActivity.reporting_year == reporting_year)))
            completeness = round(
                sum(1 for a in acts if a.is_aligned or a.is_eligible) / len(acts) * 100, 1) \
                if acts else 0.0
            status = "draft" if acts else "not_started"
        elif fw.code == FrameworkCode.CDP:
            responses = list(db.scalars(select(CDPResponse).where(
                CDPResponse.entity_id == entity_id,
                CDPResponse.reporting_year == reporting_year)))
            completeness = round(
                sum(1 for r in responses if r.answer) / len(responses) * 100, 1) \
                if responses else 0.0
            status = "draft" if responses else "not_started"
        else:
            completeness = d.completeness_pct if d else 0.0
            status = d.status if d else "not_started"
        out.append({
            "framework_code": fw.code, "framework_name": fw.name,
            "jurisdiction": fw.jurisdiction,
            "disclosure_id": d.id if d else None,
            "status": status, "completeness_pct": completeness,
            "assurance_ready": d.assurance_ready if d else False,
        })
    return {"entity_id": entity_id, "reporting_year": reporting_year, "frameworks": out}
