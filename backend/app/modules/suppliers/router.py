"""C) Supplier Engagement & Scope 3 - FR-3.C.1 to FR-3.C.5."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import assert_visible, scope_supplier_self, scoped
from app.core.serialize import page_response, rows, to_dict
from app.domain.enums import EvidenceStatus, SubmissionStatus
from app.domain.models import (
    ActionPlan, Bid, Campaign, Evidence, Notification, ProcurementDecision,
    Questionnaire, Scorecard, Submission, Supplier, SupplierInvitation,
)
from app.modules.suppliers import service

router = APIRouter(prefix="/suppliers", tags=["C) Supplier Engagement & Scope 3"])


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------

@router.get("")
def list_suppliers(
    organization_id: int | None = None, tier: int | None = None,
    category: str | None = None, country: str | None = None,
    onboarding_status: str | None = None, critical_only: bool = False,
    q: str | None = None, page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Supplier).order_by(Supplier.annual_spend.desc())
    if organization_id:
        stmt = stmt.where(Supplier.organization_id == organization_id)
    if tier:
        stmt = stmt.where(Supplier.tier == tier)
    if category:
        stmt = stmt.where(Supplier.category == category)
    if country:
        stmt = stmt.where(Supplier.country == country)
    if onboarding_status:
        stmt = stmt.where(Supplier.onboarding_status == onboarding_status)
    if critical_only:
        stmt = stmt.where(Supplier.is_critical.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Supplier.name.like(like) | Supplier.code.like(like))
    stmt = scope_supplier_self(scoped(stmt, Supplier, p), Supplier, p)

    year = date.today().year

    def mapper(s: Supplier) -> dict:
        card = db.scalars(
            select(Scorecard).where(Scorecard.supplier_id == s.id)
            .order_by(Scorecard.period_year.desc())
        ).first()
        return to_dict(s, extra={
            "score": card.overall_score if card else None,
            "maturity_level": card.maturity_level if card else None,
            "rank": card.rank if card else None,
            "tco2e": card.emissions_tco2e if card else
            round(service.supplier_emissions(db, s.id, year) / 1000, 3),
        })

    return page_response(db, stmt, page=page, page_size=page_size, mapper=mapper)


@router.get("/languages")
def supported_languages():
    """FR-3.C.1 - 25+ languages."""
    return {"count": len(settings.supported_languages),
            "languages": settings.supported_languages}


@router.get("/{supplier_id}")
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 p: Principal = Depends(get_principal)):
    s = db.get(Supplier, supplier_id)
    if s is None:
        raise HTTPException(404, "Supplier not found")
    assert_visible(p, object_type="supplier", object_id=supplier_id)
    year = date.today().year
    cards = rows(db.scalars(select(Scorecard).where(Scorecard.supplier_id == supplier_id)
                            .order_by(Scorecard.period_year.desc())))
    children = rows(db.scalars(select(Supplier)
                               .where(Supplier.parent_supplier_id == supplier_id)))
    parent = db.get(Supplier, s.parent_supplier_id) if s.parent_supplier_id else None
    return to_dict(s, extra={
        "scorecards": cards,
        "sub_tier_suppliers": children,
        "parent_supplier": to_dict(parent) if parent else None,
        "tco2e_current_year": round(service.supplier_emissions(db, supplier_id, year) / 1000, 3),
        "submissions": rows(db.scalars(select(Submission)
                                       .where(Submission.supplier_id == supplier_id))),
        "action_plans": rows(db.scalars(select(ActionPlan)
                                        .where(ActionPlan.supplier_id == supplier_id))),
    })


# ---------------------------------------------------------------------------
# FR-3.C.1  Onboarding: questionnaires, campaigns, invitations, reminders
# ---------------------------------------------------------------------------

@router.get("/questionnaires/list")
def list_questionnaires(db: Session = Depends(get_db)):
    return rows(db.scalars(select(Questionnaire).order_by(Questionnaire.name)))


@router.get("/questionnaires/{questionnaire_id}")
def get_questionnaire(questionnaire_id: int, language: str = "en",
                      db: Session = Depends(get_db)):
    q = db.get(Questionnaire, questionnaire_id)
    if q is None:
        raise HTTPException(404, "Questionnaire not found")
    questions = []
    for question in (q.questions or []):
        text = question.get("text", {})
        questions.append({
            **question,
            "text": text.get(language, text.get("en", "")) if isinstance(text, dict) else text,
        })
    return to_dict(q, extra={"questions": questions, "language": language,
                             "available_languages": q.languages})


class CampaignIn(BaseModel):
    organization_id: int
    questionnaire_id: int
    name: str
    reporting_year: int = date.today().year
    due_date: date
    reminder_cadence_days: int = 7
    supplier_ids: list[int] = Field(default_factory=list)
    materiality_threshold_spend: float | None = None


@router.post("/campaigns", status_code=201)
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("suppliers.campaign"))):
    """FR-3.C.1 - materiality-based supplier selection and invitation."""
    questionnaire = db.get(Questionnaire, payload.questionnaire_id)
    if questionnaire is None:
        raise HTTPException(404, "Questionnaire not found")

    campaign = Campaign(
        organization_id=payload.organization_id,
        questionnaire_id=payload.questionnaire_id,
        name=payload.name, reporting_year=payload.reporting_year,
        due_date=payload.due_date, status="active",
        reminder_cadence_days=payload.reminder_cadence_days,
    )
    db.add(campaign)
    db.flush()

    supplier_ids = payload.supplier_ids
    if not supplier_ids:
        stmt = select(Supplier).where(Supplier.organization_id == payload.organization_id)
        if payload.materiality_threshold_spend:
            stmt = stmt.where(Supplier.annual_spend >= payload.materiality_threshold_spend)
        supplier_ids = [s.id for s in db.scalars(stmt)]

    now = datetime.now(timezone.utc)
    for sid in supplier_ids:
        supplier = db.get(Supplier, sid)
        if supplier is None:
            continue
        language = supplier.language if supplier.language in settings.supported_languages else "en"
        db.add(SupplierInvitation(
            campaign_id=campaign.id, supplier_id=sid, language=language,
            status=SubmissionStatus.NOT_STARTED, sent_at=now,
            access_token=service.new_access_token(),
        ))
        db.add(Submission(
            campaign_id=campaign.id, supplier_id=sid,
            questionnaire_id=payload.questionnaire_id,
            reporting_year=payload.reporting_year,
            status=SubmissionStatus.NOT_STARTED, answers={},
        ))
        supplier.onboarding_status = "invited"
        db.add(Notification(
            organization_id=payload.organization_id, trigger="supplier_deadline",
            severity="info", title=f"Questionnaire due: {campaign.name}",
            body=f"{supplier.name} must respond by {payload.due_date.isoformat()}.",
            object_type="campaign", object_id=campaign.id,
            link=f"/suppliers/campaigns/{campaign.id}",
            due_at=datetime.combine(payload.due_date, datetime.min.time()),
        ))

    campaign.invited_count = len(supplier_ids)
    db.commit()
    return {**to_dict(campaign), "invited_supplier_count": len(supplier_ids)}


@router.get("/campaigns/list")
def list_campaigns(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    campaigns = db.scalars(select(Campaign).order_by(Campaign.due_date.desc())).all()
    return [{**to_dict(c), "progress": service.campaign_progress(db, c)} for c in campaigns]


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise HTTPException(404, "Campaign not found")
    invites = db.scalars(
        select(SupplierInvitation).where(SupplierInvitation.campaign_id == campaign_id)).all()
    enriched = []
    for inv in invites:
        supplier = db.get(Supplier, inv.supplier_id)
        sub = db.scalars(select(Submission).where(
            Submission.campaign_id == campaign_id,
            Submission.supplier_id == inv.supplier_id)).first()
        enriched.append({
            **to_dict(inv),
            "supplier_name": supplier.name if supplier else None,
            "supplier_country": supplier.country if supplier else None,
            "supplier_category": supplier.category if supplier else None,
            "submission_id": sub.id if sub else None,
            "submission_status": sub.status if sub else inv.status,
            "completeness_pct": sub.completeness_pct if sub else 0.0,
        })
    return {**to_dict(c), "progress": service.campaign_progress(db, c),
            "invitations": enriched}


@router.post("/campaigns/{campaign_id}/remind")
def send_reminders(campaign_id: int, db: Session = Depends(get_db),
                   p: Principal = Depends(require("suppliers.campaign"))):
    """FR-3.C.1 - reminders to suppliers who have not completed."""
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    now = datetime.now(timezone.utc)
    reminded = []
    for inv in db.scalars(select(SupplierInvitation)
                          .where(SupplierInvitation.campaign_id == campaign_id)):
        sub = db.scalars(select(Submission).where(
            Submission.campaign_id == campaign_id,
            Submission.supplier_id == inv.supplier_id)).first()
        if sub and sub.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.VALIDATED,
                                  SubmissionStatus.ATTESTED):
            continue
        inv.reminders_sent += 1
        inv.last_reminder_at = now
        supplier = db.get(Supplier, inv.supplier_id)
        reminded.append({"supplier_id": inv.supplier_id,
                         "supplier_name": supplier.name if supplier else None,
                         "language": inv.language,
                         "reminders_sent": inv.reminders_sent})
        db.add(Notification(
            organization_id=campaign.organization_id, trigger="supplier_deadline",
            severity="warning", title=f"Reminder sent: {campaign.name}",
            body=f"Reminder #{inv.reminders_sent} sent to {supplier.name if supplier else ''}.",
            object_type="campaign", object_id=campaign.id,
        ))
    db.commit()
    return {"campaign_id": campaign_id, "reminded_count": len(reminded),
            "reminded": reminded}


# ---------------------------------------------------------------------------
# FR-3.C.2  Primary-data collection
# ---------------------------------------------------------------------------

@router.get("/submissions/list")
def list_submissions(
    campaign_id: int | None = None, supplier_id: int | None = None,
    status: str | None = None, page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Submission).order_by(Submission.updated_at.desc())
    if campaign_id:
        stmt = stmt.where(Submission.campaign_id == campaign_id)
    if supplier_id:
        stmt = stmt.where(Submission.supplier_id == supplier_id)
    if status:
        stmt = stmt.where(Submission.status == status)
    stmt = scope_supplier_self(scoped(stmt, Submission, p), Submission, p)

    def mapper(s: Submission) -> dict:
        supplier = db.get(Supplier, s.supplier_id)
        return to_dict(s, extra={"supplier_name": supplier.name if supplier else None,
                                 "supplier_country": supplier.country if supplier else None})

    return page_response(db, stmt, page=page, page_size=page_size, mapper=mapper)


class SubmissionIn(BaseModel):
    answers: dict
    capture_channel: str = "form"
    submit: bool = False
    attested_by: str = ""


@router.put("/submissions/{submission_id}")
def save_submission(
    submission_id: int, payload: SubmissionIn,
    db: Session = Depends(get_db), p: Principal = Depends(require("submission.submit")),
):
    """FR-3.C.2 - forms, validations, attestations and the submission workflow."""
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(404, "Submission not found")
    if p.user.supplier_id and p.user.supplier_id != sub.supplier_id:
        raise HTTPException(403, "Suppliers may only edit their own submission (FR-7.1)")

    questionnaire = db.get(Questionnaire, sub.questionnaire_id)
    questions = (questionnaire.questions or []) if questionnaire else []

    sub.answers = {**(sub.answers or {}), **payload.answers}
    sub.capture_channel = payload.capture_channel
    sub.validation_errors = service.validate_submission(questions, sub.answers)
    sub.completeness_pct = service.completeness_of(questions, sub.answers)

    blocking = [e for e in sub.validation_errors if e["severity"] == "error"]
    if payload.submit:
        if blocking:
            sub.status = SubmissionStatus.IN_PROGRESS
            raise HTTPException(422, detail={
                "message": "Submission blocked by validation errors",
                "errors": sub.validation_errors,
                "completeness_pct": sub.completeness_pct,
            })
        sub.status = SubmissionStatus.SUBMITTED
        sub.submitted_at = datetime.now(timezone.utc)
        if payload.attested_by:
            sub.attested = True
            sub.attested_by = payload.attested_by
            sub.attested_at = datetime.now(timezone.utc)
            sub.status = SubmissionStatus.ATTESTED
        supplier = db.get(Supplier, sub.supplier_id)
        if supplier:
            supplier.onboarding_status = "responded"
    else:
        sub.status = SubmissionStatus.IN_PROGRESS

    invitation = db.scalars(select(SupplierInvitation).where(
        SupplierInvitation.campaign_id == sub.campaign_id,
        SupplierInvitation.supplier_id == sub.supplier_id)).first()
    if invitation:
        invitation.progress_pct = sub.completeness_pct
        invitation.status = sub.status
    db.commit()
    return to_dict(sub)


@router.post("/submissions/{submission_id}/review")
def review_submission(
    submission_id: int, accept: bool = Body(...), notes: str = Body(default=""),
    db: Session = Depends(get_db), p: Principal = Depends(require("suppliers.write")),
):
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(404, "Submission not found")
    sub.status = SubmissionStatus.VALIDATED if accept else SubmissionStatus.REJECTED
    sub.reviewed_by_id = p.user.id
    sub.review_notes = notes
    db.commit()
    return to_dict(sub)


class OCRIn(BaseModel):
    text: str
    supplier_id: int
    title: str = "Uploaded document"
    object_type: str = "submission"
    object_id: int | None = None


@router.post("/documents/extract")
def extract_document(payload: OCRIn, db: Session = Depends(get_db),
                     p: Principal = Depends(require("suppliers.write"))):
    """FR-3.C.2 / FR-3.D.1 - documents/OCR capture with field extraction."""
    supplier = db.get(Supplier, payload.supplier_id)
    if supplier is None:
        raise HTTPException(404, "Supplier not found")
    result = service.extract_from_document(payload.text)
    ev = Evidence(
        organization_id=supplier.organization_id,
        object_type=payload.object_type,
        object_id=payload.object_id or payload.supplier_id,
        title=payload.title, evidence_type="document",
        status=EvidenceStatus.OCR_EXTRACTED,
        ocr_text=payload.text[:20000],
        extracted_fields=result["extracted_fields"],
        uploaded_by_id=p.user.id,
    )
    db.add(ev)
    db.commit()
    return {**result, "evidence_id": ev.id}


@router.get("/{supplier_id}/evidence")
def supplier_evidence(supplier_id: int, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    assert_visible(p, object_type="supplier", object_id=supplier_id)
    return rows(db.scalars(select(Evidence).where(
        Evidence.object_type.in_(["supplier", "submission"]),
        Evidence.object_id == supplier_id)))


# ---------------------------------------------------------------------------
# FR-3.C.3  Scorecards, maturity, rankings, improvement plans
# ---------------------------------------------------------------------------

@router.post("/scorecards/compute")
def compute_scorecards(
    organization_id: int = Body(...), year: int = Body(default=date.today().year),
    db: Session = Depends(get_db), p: Principal = Depends(require("suppliers.write")),
):
    suppliers = list(db.scalars(select(Supplier)
                                .where(Supplier.organization_id == organization_id)))
    for s in suppliers:
        service.compute_scorecard(db, s, year)
    cards = service.rank_scorecards(db, year, organization_id)
    db.commit()
    return {
        "year": year, "supplier_count": len(suppliers), "scorecards_computed": len(cards),
        "maturity_distribution": {
            level: sum(1 for c in cards if c.maturity_level == level)
            for level in {c.maturity_level for c in cards}
        },
        "average_score": round(sum(c.overall_score for c in cards) / len(cards), 2)
        if cards else 0.0,
    }


@router.get("/scorecards/list")
def list_scorecards(
    year: int = Query(default=date.today().year), category: str | None = None,
    maturity_level: str | None = None, page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(Scorecard).where(Scorecard.period_year == year) \
        .order_by(Scorecard.overall_score.desc())
    if maturity_level:
        stmt = stmt.where(Scorecard.maturity_level == maturity_level)
    stmt = scope_supplier_self(scoped(stmt, Scorecard, p), Scorecard, p)

    def mapper(c: Scorecard) -> dict:
        s = db.get(Supplier, c.supplier_id)
        return to_dict(c, extra={
            "supplier_name": s.name if s else None,
            "supplier_country": s.country if s else None,
            "supplier_category": s.category if s else None,
            "supplier_tier": s.tier if s else None,
            "annual_spend": s.annual_spend if s else None,
        })

    result = page_response(db, stmt, page=page, page_size=page_size, mapper=mapper)
    if category:
        result["items"] = [i for i in result["items"] if i["supplier_category"] == category]
    return result


@router.get("/{supplier_id}/scorecard-history")
def scorecard_history(supplier_id: int, db: Session = Depends(get_db)):
    """FR-3.C.3 - year-over-year performance."""
    cards = db.scalars(select(Scorecard).where(Scorecard.supplier_id == supplier_id)
                       .order_by(Scorecard.period_year)).all()
    return {
        "supplier_id": supplier_id,
        "history": rows(cards),
        "trend": [
            {"year": c.period_year, "overall_score": c.overall_score,
             "tco2e": c.emissions_tco2e, "yoy_delta": c.yoy_delta,
             "maturity_level": c.maturity_level}
            for c in cards
        ],
    }


class ActionPlanIn(BaseModel):
    organization_id: int
    supplier_id: int | None = None
    entity_id: int | None = None
    plan_type: str = "improvement"
    title: str
    description: str = ""
    owner: str = ""
    assistance_offered: str = ""
    due_date: date | None = None
    priority: str = "medium"
    expected_abatement_tco2e: float = 0.0


@router.post("/action-plans", status_code=201)
def create_action_plan(payload: ActionPlanIn, db: Session = Depends(get_db),
                       p: Principal = Depends(require("suppliers.write"))):
    """FR-3.C.3 - improvement plans, assistance and joint reduction projects."""
    plan = ActionPlan(**payload.model_dump(),
                      object_type="supplier" if payload.supplier_id else "entity",
                      object_id=payload.supplier_id or payload.entity_id)
    db.add(plan)
    db.commit()
    return to_dict(plan)


@router.get("/action-plans/list")
def list_action_plans(
    supplier_id: int | None = None, status: str | None = None, plan_type: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    stmt = select(ActionPlan).order_by(ActionPlan.due_date)
    if supplier_id:
        stmt = stmt.where(ActionPlan.supplier_id == supplier_id)
    if status:
        stmt = stmt.where(ActionPlan.status == status)
    if plan_type:
        stmt = stmt.where(ActionPlan.plan_type == plan_type)
    return rows(db.scalars(scoped(stmt, ActionPlan, p)))


@router.patch("/action-plans/{plan_id}")
def update_action_plan(plan_id: int, payload: dict = Body(...),
                       db: Session = Depends(get_db),
                       p: Principal = Depends(require("suppliers.write"))):
    plan = db.get(ActionPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Action plan not found")
    for k, v in payload.items():
        if hasattr(plan, k) and k != "id":
            setattr(plan, k, v)
    db.commit()
    return to_dict(plan)


# ---------------------------------------------------------------------------
# FR-3.C.4  Network maps, heat maps, hotspots, outliers, resilience
# ---------------------------------------------------------------------------

@router.get("/network/map")
def network_map(organization_id: int, year: int = Query(default=date.today().year),
                db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    return service.build_network(db, organization_id, year)


@router.get("/network/resilience-scenarios")
def resilience(organization_id: int, year: int = Query(default=date.today().year),
               db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    return {
        "organization_id": organization_id, "year": year,
        "scenarios": service.resilience_scenarios(db, organization_id, year),
    }


# ---------------------------------------------------------------------------
# FR-3.C.5  Procurement decisions
# ---------------------------------------------------------------------------

@router.get("/procurement/decisions")
def list_decisions(db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    decisions = db.scalars(select(ProcurementDecision)
                           .order_by(ProcurementDecision.id.desc())).all()
    out = []
    for d in decisions:
        bids = db.scalars(select(Bid).where(Bid.decision_id == d.id)
                          .order_by(Bid.rank)).all()
        out.append({**to_dict(d), "bid_count": len(bids)})
    return out


@router.get("/procurement/decisions/{decision_id}")
def get_decision(decision_id: int, db: Session = Depends(get_db)):
    d = db.get(ProcurementDecision, decision_id)
    if d is None:
        raise HTTPException(404, "Procurement decision not found")
    bids = service.score_bids(db, d)
    db.commit()

    def bid_row(b: Bid) -> dict:
        supplier = db.get(Supplier, b.supplier_id)
        lifetime = max(b.lifetime_years or 1.0, 1.0)
        carbon_kg = ((b.embodied_kgco2e_per_unit + b.logistics_kgco2e_per_unit) * b.quantity
                     + b.annual_operating_kgco2e * lifetime)
        return to_dict(b, extra={
            "supplier_name": supplier.name if supplier else None,
            "supplier_country": supplier.country if supplier else None,
            "financial_tco": round(b.price * b.quantity + b.annual_operating_cost * lifetime, 2),
            "total_carbon_tco2e": round(carbon_kg / 1000, 3),
        })

    return {**to_dict(d),
            "bids": [bid_row(b) for b in sorted(bids, key=lambda x: x.rank)],
            "explanation": (
                f"Weighted score = 40% cost + {d.carbon_weight_pct:g}% carbon + "
                f"{max(0, 100 - 40 - d.carbon_weight_pct):g}% quality. Carbon is also "
                f"monetised at {d.internal_carbon_price:g}/tCO2e inside the "
                "carbon-inclusive TCO."
            )}


class DecisionIn(BaseModel):
    organization_id: int
    title: str
    category: str = ""
    carbon_weight_pct: float = 20.0
    internal_carbon_price: float = 0.0
    bids: list[dict] = Field(default_factory=list)


@router.post("/procurement/decisions", status_code=201)
def create_decision(payload: DecisionIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require("suppliers.write"))):
    """FR-3.C.5 - carbon-weighted bids and carbon-inclusive TCO."""
    d = ProcurementDecision(
        organization_id=payload.organization_id, title=payload.title,
        category=payload.category, carbon_weight_pct=payload.carbon_weight_pct,
        internal_carbon_price=payload.internal_carbon_price,
    )
    db.add(d)
    db.flush()
    for raw in payload.bids:
        db.add(Bid(decision_id=d.id, **raw))
    db.flush()
    service.score_bids(db, d)
    db.commit()
    return get_decision(d.id, db)


@router.post("/procurement/decisions/{decision_id}/award")
def award_decision(decision_id: int, bid_id: int = Body(...), notes: str = Body(default=""),
                   db: Session = Depends(get_db),
                   p: Principal = Depends(require("suppliers.write"))):
    d = db.get(ProcurementDecision, decision_id)
    bid = db.get(Bid, bid_id)
    if d is None or bid is None or bid.decision_id != decision_id:
        raise HTTPException(404, "Decision or bid not found")
    d.awarded_bid_id = bid_id
    d.status = "awarded"
    d.decision_notes = notes
    supplier = db.get(Supplier, bid.supplier_id)
    if supplier:
        supplier.has_data_agreement = True
        clauses = list(supplier.contract_clauses or [])
        clauses.append({
            "clause": "Annual product carbon footprint disclosure",
            "added_at": datetime.now(timezone.utc).isoformat(),
            "decision_id": decision_id,
        })
        supplier.contract_clauses = clauses
    db.commit()
    return {"decision_id": decision_id, "awarded_bid_id": bid_id,
            "supplier": supplier.name if supplier else None,
            "contract_clauses": supplier.contract_clauses if supplier else []}


@router.get("/procurement/category-strategy")
def category_strategy(organization_id: int, year: int = Query(default=date.today().year),
                      db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-3.C.5 - category strategies, KPIs, audits and data agreements."""
    network = service.build_network(db, organization_id, year)
    suppliers = list(db.scalars(select(Supplier)
                                .where(Supplier.organization_id == organization_id)))
    strategies = []
    for cat in network["category_hotspots"]:
        in_cat = [s for s in suppliers if (s.category or "uncategorized") == cat["category"]]
        with_agreement = sum(1 for s in in_cat if s.has_data_agreement)
        engaged = sum(1 for s in in_cat if s.onboarding_status in ("invited", "responded"))
        strategies.append({
            "category": cat["category"],
            "tco2e": cat["tco2e"],
            "share_pct": cat["share_pct"],
            "spend": round(cat["spend"], 2),
            "supplier_count": cat["supplier_count"],
            "intensity_tco2e_per_m_spend": round(
                cat["tco2e"] / cat["spend"] * 1_000_000, 3) if cat["spend"] else 0.0,
            "kpis": {
                "data_agreement_coverage_pct": round(
                    with_agreement / len(in_cat) * 100, 1) if in_cat else 0.0,
                "engagement_coverage_pct": round(
                    engaged / len(in_cat) * 100, 1) if in_cat else 0.0,
                "critical_suppliers": sum(1 for s in in_cat if s.is_critical),
                "audit_due": sum(1 for s in in_cat if s.risk_rating == "high"),
            },
            "recommended_clauses": [
                "Annual Scope 1-2 disclosure with third-party assurance",
                "Product carbon footprint on request within 60 days",
                "Reduction target aligned to 1.5C by contract renewal",
            ] if cat["share_pct"] >= 5 else [
                "Annual Scope 1-2 disclosure",
            ],
            "priority": "high" if cat["share_pct"] >= 15 else
                        "medium" if cat["share_pct"] >= 5 else "low",
        })
    return {"organization_id": organization_id, "year": year, "strategies": strategies}
