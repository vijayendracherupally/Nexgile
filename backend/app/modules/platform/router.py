"""7) Key Functional Requirements - FR-7.1, .5, .6, .7 (and the workflow spine).

FR-7.2 lives in engine/lineage.py, FR-7.3 in engine/recalc.py, FR-7.4 in the
analytics module, and FR-7.8 in core/scoping.py. This module implements access
administration, cross-object search, notifications/workflows and bulk/exports.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.rbac import PERMISSIONS, Principal, get_principal, require
from app.core.scoping import ScenarioContext, get_scenario_context, scoped
from app.core.serialize import page_response, rows, to_dict
from app.domain.enums import CalculationStatus, JobStatus, RoleGroup
from app.domain.models import (
    ActionPlan, ActivityData, Anomaly, Approval, AuditLog, Calculation, Campaign,
    Category, CreditOffset, DataGap, DataPoint, Disclosure, Emission, EmissionFactor,
    Entity, Evidence, Facility, Framework, Job, Notification, Organization, PCF,
    Product, ReductionInitiative, Report, Role, SavedView, Scenario, Submission,
    Supplier, Target, User, UserScope,
)
from app.engine import lineage
from app.engine.calculator import CalculationOptions, calculate_batch
from app.modules.suppliers import service as supplier_service

router = APIRouter(prefix="/platform", tags=["7) Platform - access, search, workflow, bulk"])


# ---------------------------------------------------------------------------
# FR-7.1  Access administration
# ---------------------------------------------------------------------------

@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    return p.as_dict()


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    return {
        "groups": [g.value for g in RoleGroup],
        "permissions": PERMISSIONS,
        "roles": rows(db.scalars(select(Role).order_by(Role.group, Role.name))),
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    users = db.scalars(select(User).order_by(User.full_name)).all()
    out = []
    for u in users:
        grants = db.scalars(select(UserScope).where(UserScope.user_id == u.id)).all()
        out.append({**to_dict(u), "role_code": u.role.code, "role_name": u.role.name,
                    "role_group": u.role.group,
                    "grants": [{"object_type": g.object_type, "object_id": g.object_id}
                               for g in grants]})
    return out


@router.get("/access-check")
def access_check(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """Shows exactly what this principal can see - FR-7.1 made inspectable."""
    def count(model, ids: set[int]) -> dict:
        total = db.scalar(select(func.count()).select_from(model)) or 0
        visible = len(ids) if not p.is_unrestricted else total
        return {"visible": visible, "total": total,
                "restricted": not p.is_unrestricted and visible < total}

    return {
        "principal": p.as_dict(),
        "visibility": {
            "organizations": count(Organization, p.organization_ids),
            "entities": count(Entity, p.entity_ids),
            "facilities": count(Facility, p.facility_ids),
            "suppliers": count(Supplier, p.supplier_ids),
            "products": count(Product, p.product_ids),
            "calculations": {
                "visible": db.scalar(
                    select(func.count()).select_from(Calculation)) if p.is_unrestricted
                else db.scalar(select(func.count()).select_from(Calculation).where(
                    Calculation.activity_data_id.in_(
                        select(ActivityData.id).where(
                            ActivityData.entity_id.in_(p.entity_ids or {0}))))) or 0,
                "total": db.scalar(select(func.count()).select_from(Calculation)) or 0,
            },
            "evidence": count(Evidence, p.organization_ids),
            "reports": count(Report, p.organization_ids),
        },
        "enforced_by": "app/core/scoping.py :: scoped() - applied at the repository layer",
    }


class GrantIn(BaseModel):
    user_id: int
    object_type: str
    object_id: int


@router.post("/grants", status_code=201)
def create_grant(payload: GrantIn, db: Session = Depends(get_db),
                 p: Principal = Depends(require("platform.admin"))):
    existing = db.scalars(select(UserScope).where(
        UserScope.user_id == payload.user_id,
        UserScope.object_type == payload.object_type,
        UserScope.object_id == payload.object_id)).first()
    if existing:
        return to_dict(existing)
    g = UserScope(**payload.model_dump())
    db.add(g)
    lineage.record_change(db, action="grant", object_type="user_scope", object_id=0,
                          user_id=p.user.id, user_email=p.user.email,
                          after=payload.model_dump())
    db.commit()
    return to_dict(g)


@router.delete("/grants/{grant_id}")
def revoke_grant(grant_id: int, db: Session = Depends(get_db),
                 p: Principal = Depends(require("platform.admin"))):
    g = db.get(UserScope, grant_id)
    if g is None:
        raise HTTPException(404, "Grant not found")
    before = to_dict(g)
    db.delete(g)
    lineage.record_change(db, action="revoke", object_type="user_scope",
                          object_id=grant_id, user_id=p.user.id,
                          user_email=p.user.email, before=before)
    db.commit()
    return {"revoked": grant_id}


# ---------------------------------------------------------------------------
# FR-7.5  Search and navigation with filters and saved views
# ---------------------------------------------------------------------------

SEARCHABLE = ["entity", "facility", "source", "product", "supplier", "emission_factor",
              "calculation", "disclosure", "evidence", "action"]


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    types: str | None = Query(default=None,
                              description="Comma-separated subset of the searchable types"),
    limit_per_type: int = 10,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    """FR-7.5 - one search across every object family the document names."""
    wanted = [t.strip() for t in types.split(",")] if types else SEARCHABLE
    like = f"%{q}%"
    results: dict[str, list] = {}

    def add(kind: str, items, mapper):
        if kind in wanted:
            results[kind] = [mapper(i) for i in items]

    if "entity" in wanted:
        add("entity", db.scalars(scoped(
            select(Entity).where(or_(Entity.name.like(like), Entity.code.like(like)))
            .limit(limit_per_type), Entity, p)),
            lambda e: {"id": e.id, "label": e.name, "sublabel": f"{e.code} - {e.country}",
                       "route": f"/organization/entities/{e.id}"})
    if "facility" in wanted:
        add("facility", db.scalars(scoped(
            select(Facility).where(or_(Facility.name.like(like), Facility.code.like(like)))
            .limit(limit_per_type), Facility, p)),
            lambda f: {"id": f.id, "label": f.name,
                       "sublabel": f"{f.facility_type} - {f.country}",
                       "route": f"/organization/facilities/{f.id}"})
    if "source" in wanted:
        from app.domain.models import Source
        add("source", db.scalars(scoped(
            select(Source).where(or_(Source.name.like(like),
                                     Source.activity_key.like(like)))
            .limit(limit_per_type), Source, p)),
            lambda s: {"id": s.id, "label": s.name,
                       "sublabel": f"{s.scope} - {s.source_type}",
                       "route": f"/accounting/sources/{s.id}"})
    if "product" in wanted:
        add("product", db.scalars(scoped(
            select(Product).where(or_(Product.name.like(like), Product.sku.like(like)))
            .limit(limit_per_type), Product, p)),
            lambda pr: {"id": pr.id, "label": f"{pr.sku} - {pr.name}",
                        "sublabel": pr.category, "route": f"/lca/products/{pr.id}"})
    if "supplier" in wanted:
        add("supplier", db.scalars(scoped(
            select(Supplier).where(or_(Supplier.name.like(like), Supplier.code.like(like)))
            .limit(limit_per_type), Supplier, p)),
            lambda s: {"id": s.id, "label": s.name,
                       "sublabel": f"Tier {s.tier} - {s.country}",
                       "route": f"/suppliers/{s.id}"})
    if "emission_factor" in wanted:
        add("emission_factor", db.scalars(
            select(EmissionFactor).where(or_(EmissionFactor.name.like(like),
                                             EmissionFactor.activity_key.like(like)))
            .limit(limit_per_type)),
            lambda f: {"id": f.id, "label": f.name,
                       "sublabel": f"{f.value_kgco2e} kgCO2e/{f.unit} - {f.country}",
                       "route": f"/accounting/factors/{f.id}"})
    if "calculation" in wanted:
        matching_activities = select(ActivityData.id).where(
            or_(ActivityData.description.like(like), ActivityData.activity_key.like(like)))
        add("calculation", db.scalars(
            select(Calculation).where(Calculation.activity_data_id.in_(matching_activities))
            .limit(limit_per_type)),
            lambda c: {"id": c.id, "label": f"Calculation #{c.id}",
                       "sublabel": f"{c.consolidated_co2e_kg:.2f} kgCO2e - {c.status}",
                       "route": f"/accounting/calculations/{c.id}"})
    if "disclosure" in wanted:
        add("disclosure", db.scalars(scoped(
            select(Disclosure).where(Disclosure.title.like(like)).limit(limit_per_type),
            Disclosure, p)),
            lambda d: {"id": d.id, "label": d.title,
                       "sublabel": f"{d.reporting_year} - {d.status}",
                       "route": f"/compliance/disclosures/{d.id}"})
    if "evidence" in wanted:
        add("evidence", db.scalars(scoped(
            select(Evidence).where(Evidence.title.like(like)).limit(limit_per_type),
            Evidence, p)),
            lambda e: {"id": e.id, "label": e.title,
                       "sublabel": f"{e.evidence_type} - {e.status}",
                       "route": f"/compliance/evidence/{e.id}"})
    if "action" in wanted:
        add("action", db.scalars(scoped(
            select(ActionPlan).where(ActionPlan.title.like(like)).limit(limit_per_type),
            ActionPlan, p)),
            lambda a: {"id": a.id, "label": a.title,
                       "sublabel": f"{a.plan_type} - {a.status}",
                       "route": f"/suppliers/action-plans/{a.id}"})

    return {
        "query": q,
        "searchable_types": SEARCHABLE,
        "result_count": sum(len(v) for v in results.values()),
        "results": results,
    }


@router.get("/saved-views")
def list_saved_views(object_type: str | None = None, db: Session = Depends(get_db),
                     p: Principal = Depends(get_principal)):
    stmt = select(SavedView).where(
        or_(SavedView.user_id == p.user.id, SavedView.is_shared.is_(True)))
    if object_type:
        stmt = stmt.where(SavedView.object_type == object_type)
    return rows(db.scalars(stmt.order_by(SavedView.name)))


class SavedViewIn(BaseModel):
    name: str
    object_type: str
    filters: dict = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    sort: str = ""
    is_shared: bool = False


@router.post("/saved-views", status_code=201)
def create_saved_view(payload: SavedViewIn, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    v = SavedView(user_id=p.user.id, **payload.model_dump())
    db.add(v)
    db.commit()
    return to_dict(v)


@router.delete("/saved-views/{view_id}")
def delete_saved_view(view_id: int, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    v = db.get(SavedView, view_id)
    if v is None:
        raise HTTPException(404, "Saved view not found")
    if v.user_id != p.user.id:
        raise HTTPException(403, "You may only delete your own saved views")
    db.delete(v)
    db.commit()
    return {"deleted": view_id}


# ---------------------------------------------------------------------------
# FR-7.6  Notifications and workflows
# ---------------------------------------------------------------------------

NOTIFICATION_TRIGGERS = [
    "missing_data", "supplier_deadline", "validation_failure", "target_deviation",
    "factor_update", "approval_required", "assurance_request", "regulatory_update",
]


@router.get("/notifications")
def list_notifications(unread_only: bool = False, trigger: str | None = None,
                       page: int = 1, page_size: int = 50,
                       db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    if trigger:
        stmt = stmt.where(Notification.trigger == trigger)
    stmt = stmt.where(or_(Notification.user_id == p.user.id,
                          Notification.user_id.is_(None)))
    return page_response(db, scoped(stmt, Notification, p), page=page, page_size=page_size)


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db),
              p: Principal = Depends(get_principal)):
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return to_dict(n)


@router.post("/notifications/scan")
def scan_notifications(organization_id: int = Body(..., embed=True),
                       db: Session = Depends(get_db),
                       p: Principal = Depends(require("platform.admin"))):
    """FR-7.6 - evaluates all eight triggers the document lists and raises
    notifications for anything outstanding."""
    created: list[dict] = []
    now = datetime.now(timezone.utc)
    year = date.today().year

    def raise_notification(trigger: str, severity: str, title: str, body: str,
                           object_type: str = "", object_id: int | None = None,
                           link: str = ""):
        existing = db.scalars(select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.trigger == trigger, Notification.title == title,
            Notification.is_read.is_(False))).first()
        if existing:
            return
        n = Notification(organization_id=organization_id, trigger=trigger,
                         severity=severity, title=title, body=body,
                         object_type=object_type, object_id=object_id, link=link)
        db.add(n)
        created.append({"trigger": trigger, "title": title, "severity": severity})

    # 1. missing data
    for gap in db.scalars(select(DataGap).where(DataGap.status == "open").limit(50)):
        raise_notification("missing_data", "warning",
                           f"Missing data: {gap.description[:120]}",
                           f"Estimated impact {gap.estimated_co2e_kg / 1000:.2f} tCO2e.",
                           "data_gap", gap.id, "/analytics/gaps")

    # 2. supplier deadlines
    for c in db.scalars(select(Campaign).where(Campaign.status == "active")):
        progress = supplier_service.campaign_progress(db, c)
        if progress["days_remaining"] is not None and progress["days_remaining"] <= 14:
            raise_notification(
                "supplier_deadline",
                "critical" if progress["is_overdue"] else "warning",
                f"Campaign '{c.name}' due in {progress['days_remaining']} day(s)",
                f"{progress['responded']}/{progress['invited']} suppliers have responded.",
                "campaign", c.id, f"/suppliers/campaigns/{c.id}")

    # 3. validation failures
    open_anomalies = db.scalar(select(func.count()).select_from(Anomaly)
                               .where(Anomaly.status == "open")) or 0
    if open_anomalies:
        raise_notification("validation_failure", "warning",
                           f"{open_anomalies} open data anomalies",
                           "Review the anomaly inbox and resolve or accept each flag.",
                           "anomaly", None, "/analytics/anomalies")

    # 4. target deviations
    for t in db.scalars(select(Target)):
        actual_kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.entity_id == t.entity_id, Emission.year == year,
            Emission.scenario_id.is_(None))) or 0.0
        span = max(1, t.target_year - t.base_year)
        allowed = t.base_value * (1 - t.reduction_pct / 100 * (year - t.base_year) / span)
        if float(actual_kg) / 1000 > allowed:
            entity = db.get(Entity, t.entity_id)
            raise_notification(
                "target_deviation", "critical",
                f"Target off track: {t.name}",
                f"{entity.name if entity else ''} is at "
                f"{float(actual_kg) / 1000:.1f} tCO2e against an allowance of "
                f"{allowed:.1f} tCO2e for {year}.",
                "target", t.id, "/dashboards/targets")

    # 5. factor updates
    from app.domain.models import FactorLibrary
    for lib in db.scalars(select(FactorLibrary).where(FactorLibrary.is_locked.is_(False))):
        if lib.release_date and (date.today() - lib.release_date).days <= 365:
            raise_notification("factor_update", "info",
                               f"Factor library available: {lib.provider} {lib.version}",
                               "Run a recalculation impact analysis before adopting it.",
                               "factor_library", lib.id, "/accounting/factors")

    # 6. approvals
    pending = db.scalar(select(func.count()).select_from(Calculation)
                        .where(Calculation.status == CalculationStatus.CALCULATED)) or 0
    if pending:
        raise_notification("approval_required", "info",
                           f"{pending} calculations awaiting approval",
                           "Approve to freeze the values for reporting.",
                           "calculation", None, "/accounting/approvals")

    # 7. assurance requests
    from app.domain.models import AssuranceRequest
    for a in db.scalars(select(AssuranceRequest).where(
            AssuranceRequest.status.in_(["requested", "in_progress"]))):
        raise_notification("assurance_request", "info",
                           f"Assurance in progress with {a.assurer}",
                           f"{a.assurance_level} assurance, "
                           f"due {a.due_date.isoformat() if a.due_date else 'unscheduled'}.",
                           "assurance_request", a.id, "/compliance/assurance")

    # 8. regulatory updates
    for fw in db.scalars(select(Framework).where(Framework.is_active.is_(True))):
        raise_notification("regulatory_update", "info",
                           f"{fw.code} reporting window open for {year}",
                           f"{fw.name} - {fw.jurisdiction}. Check readiness.",
                           "framework", fw.id, "/compliance")

    db.commit()
    return {"scanned_at": now.isoformat(), "created": len(created),
            "notifications": created, "triggers_evaluated": NOTIFICATION_TRIGGERS}


@router.get("/approvals")
def list_approvals(status: str | None = None, object_type: str | None = None,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Approval).order_by(Approval.created_at.desc())
    if status:
        stmt = stmt.where(Approval.status == status)
    if object_type:
        stmt = stmt.where(Approval.object_type == object_type)
    return rows(db.scalars(stmt))


class ApprovalIn(BaseModel):
    object_type: str
    object_id: int
    step: str = "review"
    assigned_to_id: int | None = None
    comment: str = ""


@router.post("/approvals", status_code=201)
def request_approval(payload: ApprovalIn, db: Session = Depends(get_db),
                     p: Principal = Depends(get_principal)):
    a = Approval(**payload.model_dump(), requested_by_id=p.user.id, status="pending")
    db.add(a)
    db.commit()
    return to_dict(a)


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: int, approve: bool = Body(...),
                    comment: str = Body(default=""),
                    db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    a = db.get(Approval, approval_id)
    if a is None:
        raise HTTPException(404, "Approval not found")
    a.status = "approved" if approve else "rejected"
    a.decided_by_id = p.user.id
    a.decided_at = datetime.now(timezone.utc)
    a.comment = comment
    lineage.record_change(db, action=a.status, object_type=a.object_type,
                          object_id=a.object_id, user_id=p.user.id,
                          user_email=p.user.email, reason=comment)
    db.commit()
    return to_dict(a)


# ---------------------------------------------------------------------------
# FR-7.7  Bulk operations and exports
# ---------------------------------------------------------------------------

BULK_OPERATIONS = [
    "activity_import", "factor_import", "supplier_campaign", "calculation_batch",
    "evidence_pack", "pcf_exchange", "disclosure_table", "scheduled_report",
]


def _run_job(db: Session, job: Job, principal: Principal) -> None:
    """Executes a bulk operation synchronously and records the outcome."""
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    db.flush()
    params = job.params or {}
    try:
        if job.job_type == "calculation_batch":
            stmt = select(ActivityData).where(ActivityData.scenario_id.is_(None))
            if params.get("entity_id"):
                stmt = stmt.where(ActivityData.entity_id == params["entity_id"])
            done = select(Calculation.activity_data_id).where(
                Calculation.scenario_id.is_(None))
            stmt = stmt.where(ActivityData.id.not_in(done))
            activities = list(db.scalars(scoped(stmt, ActivityData, principal)))
            job.result = calculate_batch(db, activities, CalculationOptions())
        elif job.job_type == "evidence_pack":
            job.result = _build_evidence_pack(db, params, principal)
        elif job.job_type == "disclosure_table":
            job.result = _build_disclosure_table(db, params, principal)
        elif job.job_type == "pcf_exchange":
            from app.modules.lca import service as lca_service
            pcfs = list(db.scalars(select(PCF).where(PCF.scenario_id.is_(None))))
            fmt = params.get("format", "pact")
            job.result = {
                "format": fmt, "count": len(pcfs),
                "documents": [lca_service.exchange_payload(db, pcf, fmt) for pcf in pcfs[:200]],
            }
        elif job.job_type == "supplier_campaign":
            campaign = db.get(Campaign, params.get("campaign_id", 0))
            job.result = supplier_service.campaign_progress(db, campaign) if campaign \
                else {"error": "campaign not found"}
        elif job.job_type == "scheduled_report":
            job.result = _generate_report(db, params, principal)
        else:
            job.result = {"note": f"'{job.job_type}' accepted; no synchronous work required."}
        job.status = JobStatus.COMPLETED
        job.progress_pct = 100.0
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
    job.finished_at = datetime.now(timezone.utc)
    db.flush()


def _build_evidence_pack(db: Session, params: dict, principal: Principal) -> dict:
    entity_id = params.get("entity_id")
    year = params.get("year", date.today().year)
    stmt = select(Emission).where(Emission.year == year, Emission.scenario_id.is_(None))
    if entity_id:
        stmt = stmt.where(Emission.entity_id == entity_id)
    emissions = list(db.scalars(scoped(stmt, Emission, principal)))
    traces, audit_grade = [], 0
    for e in emissions[:300]:
        try:
            trace = lineage.read(db, e.calculation_id)
        except LookupError:
            continue
        complete = trace.get("completeness", {}).get("is_audit_grade", False)
        audit_grade += int(complete)
        traces.append({
            "emission_id": e.id, "calculation_id": e.calculation_id,
            "scope": e.scope, "co2e_kg": round(e.co2e_kg, 3),
            "status": e.status, "audit_grade": complete,
            "factor": trace.get("emission_factor", {}).get("name"),
            "factor_library": (trace.get("emission_factor", {})
                               .get("library", {}).get("version")),
            "method": trace.get("method", {}).get("method"),
            "gwp_set": trace.get("method", {}).get("gwp_set"),
            "approvals": len(trace.get("approvals", [])),
            "changes": len(trace.get("timestamped_changes", [])),
            "missing_lineage": trace.get("completeness", {}).get("missing", []),
        })
    documents = db.scalars(select(Evidence)).all()
    return {
        "pack_id": f"EVIDENCE-{entity_id or 'ALL'}-{year}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_id": entity_id, "year": year,
        "value_count": len(traces),
        "audit_grade_count": audit_grade,
        "audit_grade_pct": round(audit_grade / len(traces) * 100, 1) if traces else 0.0,
        "total_tco2e": round(sum(e.co2e_kg for e in emissions) / 1000, 3),
        "supporting_documents": len(documents),
        "traces": traces,
    }


def _build_disclosure_table(db: Session, params: dict, principal: Principal) -> dict:
    disclosure_id = params.get("disclosure_id")
    if not disclosure_id:
        raise ValueError("disclosure_id is required for a disclosure table export")
    d = db.get(Disclosure, disclosure_id)
    if d is None:
        raise ValueError("Disclosure not found")
    points = db.scalars(select(DataPoint).where(DataPoint.disclosure_id == d.id)
                        .order_by(DataPoint.code)).all()
    fw = db.get(Framework, d.framework_id)
    return {
        "disclosure_id": d.id, "framework": fw.code if fw else None,
        "reporting_year": d.reporting_year, "status": d.status,
        "rows": [
            {"code": dp.code, "label": dp.label, "unit": dp.unit,
             "value": dp.value_numeric if dp.value_numeric is not None else dp.value_text,
             "xbrl_tag": dp.xbrl_tag, "verification_status": dp.verification_status,
             "source_calculations": len(dp.source_calculation_ids or []),
             "is_material": dp.is_material}
            for dp in points
        ],
    }


def _generate_report(db: Session, params: dict, principal: Principal) -> dict:
    report_id = params.get("report_id")
    report = db.get(Report, report_id) if report_id else None
    if report is None:
        raise ValueError("report_id is required")
    year = report.reporting_year
    stmt = select(Emission).where(Emission.year == year, Emission.scenario_id.is_(None))
    if report.entity_id:
        stmt = stmt.where(Emission.entity_id == report.entity_id)
    emissions = list(db.scalars(scoped(stmt, Emission, principal)))
    by_scope: dict[str, float] = {}
    for e in emissions:
        by_scope[e.scope] = by_scope.get(e.scope, 0.0) + e.co2e_kg / 1000
    payload = {
        "report": report.name, "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_tco2e": round(sum(by_scope.values()), 3),
        "by_scope": {k: round(v, 3) for k, v in by_scope.items()},
        "record_count": len(emissions),
    }
    report.payload = payload
    report.last_generated_at = datetime.now(timezone.utc)
    report.status = "generated"
    return payload


class JobIn(BaseModel):
    organization_id: int
    job_type: str
    label: str = ""
    params: dict = Field(default_factory=dict)


@router.post("/bulk/jobs", status_code=201)
def create_job(payload: JobIn, db: Session = Depends(get_db),
               p: Principal = Depends(require("bulk.execute"))):
    """FR-7.7 - every bulk operation runs as a tracked job."""
    if payload.job_type not in BULK_OPERATIONS:
        raise HTTPException(400, f"job_type must be one of {BULK_OPERATIONS}")
    job = Job(organization_id=payload.organization_id, job_type=payload.job_type,
              label=payload.label or payload.job_type, params=payload.params,
              created_by_id=p.user.id)
    db.add(job)
    db.flush()
    _run_job(db, job, p)
    db.commit()
    return to_dict(job)


@router.get("/bulk/jobs")
def list_jobs(job_type: str | None = None, status: str | None = None,
              page: int = 1, page_size: int = 50,
              db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Job).order_by(Job.id.desc())
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    if status:
        stmt = stmt.where(Job.status == status)
    return page_response(db, scoped(stmt, Job, p), page=page, page_size=page_size,
                         mapper=lambda j: to_dict(j, exclude={"result"}))


@router.get("/bulk/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return to_dict(job)


@router.get("/bulk/operations")
def bulk_operations():
    return {"operations": BULK_OPERATIONS,
            "export_formats": ["json", "csv"],
            "note": "Each maps to a bullet of FR-7.7."}


EXPORTABLE = {
    "emissions": Emission, "activity_data": ActivityData, "calculations": Calculation,
    "suppliers": Supplier, "products": Product, "emission_factors": EmissionFactor,
    "credits": CreditOffset, "evidence": Evidence, "reduction_initiatives": ReductionInitiative,
}


@router.get("/exports/{dataset}")
def export_dataset(
    dataset: str, format: str = Query(default="csv", pattern="^(csv|json)$"),
    year: int | None = None, entity_id: int | None = None, limit: int = 5000,
    db: Session = Depends(get_db), p: Principal = Depends(require("export.execute")),
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    """FR-7.7 - exports for every core dataset, respecting FR-7.1 scoping."""
    if dataset not in EXPORTABLE:
        raise HTTPException(400, f"dataset must be one of {list(EXPORTABLE)}")
    model = EXPORTABLE[dataset]
    stmt = select(model)
    if year is not None and hasattr(model, "year"):
        stmt = stmt.where(model.year == year)
    if entity_id is not None and hasattr(model, "entity_id"):
        stmt = stmt.where(model.entity_id == entity_id)
    stmt = ctx.filter(scoped(stmt, model, p), model)
    records = rows(db.scalars(stmt.limit(limit)))

    if format == "json":
        return {"dataset": dataset, "count": len(records), "items": records}

    if not records:
        return PlainTextResponse("", media_type="text/csv")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()),
                            extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                         for k, v in r.items()})
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{dataset}.csv"'})


@router.get("/reports")
def list_reports(organization_id: int | None = None, scheduled_only: bool = False,
                 db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Report).order_by(Report.id.desc())
    if organization_id:
        stmt = stmt.where(Report.organization_id == organization_id)
    if scheduled_only:
        stmt = stmt.where(Report.is_scheduled.is_(True))
    return rows(db.scalars(scoped(stmt, Report, p)),
                exclude={"payload"})


class ReportIn(BaseModel):
    organization_id: int
    name: str
    report_type: str
    entity_id: int | None = None
    framework_id: int | None = None
    reporting_year: int = date.today().year
    format: str = "json"
    is_scheduled: bool = False
    schedule_cron: str = ""
    recipients: list[str] = Field(default_factory=list)


@router.post("/reports", status_code=201)
def create_report(payload: ReportIn, db: Session = Depends(get_db),
                  p: Principal = Depends(require("export.execute"))):
    """FR-7.7 - scheduled reports."""
    r = Report(**payload.model_dump())
    db.add(r)
    db.commit()
    return to_dict(r, exclude={"payload"})


@router.post("/reports/{report_id}/generate")
def generate_report(report_id: int, db: Session = Depends(get_db),
                    p: Principal = Depends(require("export.execute"))):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    job = Job(organization_id=r.organization_id, job_type="scheduled_report",
              label=f"Generate '{r.name}'", params={"report_id": report_id},
              created_by_id=p.user.id)
    db.add(job)
    db.flush()
    _run_job(db, job, p)
    db.commit()
    return {"report": to_dict(r, exclude={"payload"}), "job": to_dict(job)}


# ---------------------------------------------------------------------------
# Platform overview - the home screen payload
# ---------------------------------------------------------------------------

@router.get("/overview")
def overview(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    year = date.today().year
    counts = {
        "organizations": db.scalar(select(func.count()).select_from(Organization)) or 0,
        "entities": db.scalar(select(func.count()).select_from(Entity)) or 0,
        "facilities": db.scalar(select(func.count()).select_from(Facility)) or 0,
        "suppliers": db.scalar(select(func.count()).select_from(Supplier)) or 0,
        "products": db.scalar(select(func.count()).select_from(Product)) or 0,
        "activity_data": db.scalar(select(func.count()).select_from(ActivityData)) or 0,
        "calculations": db.scalar(select(func.count()).select_from(Calculation)) or 0,
        "emission_factors": db.scalar(select(func.count()).select_from(EmissionFactor)) or 0,
        "pcfs": db.scalar(select(func.count()).select_from(PCF)) or 0,
        "disclosures": db.scalar(select(func.count()).select_from(Disclosure)) or 0,
        "evidence": db.scalar(select(func.count()).select_from(Evidence)) or 0,
        "scenarios": db.scalar(select(func.count()).select_from(Scenario)) or 0,
    }
    total_kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0))
                         .where(Emission.year == year,
                                Emission.scenario_id.is_(None))) or 0.0
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.is_read.is_(False))) or 0
    pending = db.scalar(select(func.count()).select_from(Calculation)
                        .where(Calculation.status == CalculationStatus.CALCULATED)) or 0
    return {
        "platform": settings.app_name,
        "version": settings.version,
        "year": year,
        "principal": p.as_dict(),
        "counts": counts,
        "total_tco2e_current_year": round(float(total_kg) / 1000, 3),
        "unread_notifications": unread,
        "pending_approvals": pending,
        "supported_languages": len(settings.supported_languages),
    }
