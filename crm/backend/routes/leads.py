"""
RankBuilder CRM — Leads API Routes
POST   /api/leads          — Create a new lead (agent-facing)
GET    /api/leads          — List leads (filterable)
GET    /api/leads/{id}     — Get single lead
PATCH  /api/leads/{id}     — Update lead (status, type, notes, etc.)
DELETE /api/leads/{id}     — Delete lead
POST   /api/leads/{id}/history — Add a note/transition to history
"""

import threading
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.scoring import compute_score

from backend.database import (
    get_db, Lead, LeadHistory, LeadSource, LeadStatus, LeadType,
    LeadActivity, EmailLog,
)
from backend.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListResponse,
    LeadHistoryItem,
    LeadHistoryResponse,
    LeadAssignRequest,
    LeadFollowUpRequest,
    LeadFollowUpResponse,
    LeadActivityItem,
    LeadActivityResponse,
    EmailLogCreate,
    EmailLogItem,
    EmailLogResponse,
)
from backend.notifications import notify_new_lead, notify_lead_sent, notify_lead_allocated, notify_hot_lead
from backend.dedupe import find_duplicate, merge_duplicate
from backend.assignment import (
    resolve_rep_for_location,
    assign_lead,
    log_follow_up,
    due_for_follow_up,
)
from backend.routes.auth import (
    get_current_user,
    require_admin_or_owner,
    enforce_client_scope,
    enforce_agent_assignment,
)
from backend.database import UserRole
from backend.database import User

# Thread pool for async notification dispatch
_executor = ThreadPoolExecutor(max_workers=4)


def _notify_async(trigger: str, lead_id: str, db: Session):
    """Fire notification in background thread with its own DB session."""
    try:
        from backend.database import SessionLocal
        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return
            lead_dict = {
                "id": lead.id,
                "client_id": lead.client_id,
                "source": lead.source.value if hasattr(lead.source, "value") else str(lead.source),
                "source_query": lead.source_query,
                "status": lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                "lead_type": lead.lead_type.value if hasattr(lead.lead_type, "value") else str(lead.lead_type) if lead.lead_type else None,
                "quality_score": lead.quality_score,
                "contact_name": lead.contact_name,
                "contact_email": lead.contact_email,
                "contact_phone": lead.contact_phone,
                "company_name": lead.company_name,
                "company_website": lead.company_website,
                "message_excerpt": lead.message_excerpt,
                "pitch_sent": lead.pitch_sent,
                "sent_to_client_at": str(lead.sent_to_client_at) if lead.sent_to_client_at else None,
                "notes": lead.notes,
                "assigned_to": lead.assigned_to,
                "assigned_to_name": lead.assigned_to_name,
                "location": lead.location,
                "allocated_by": getattr(lead, "_allocated_by", None) or "system",
            }
            if trigger == "new_lead":
                notify_new_lead(lead_dict, db=session)
            elif trigger == "lead_sent":
                notify_lead_sent(lead_dict, db=session)
            elif trigger == "lead_allocated":
                notify_lead_allocated(
                    lead_dict,
                    rep_email=lead_dict.get("assigned_to") or "",
                    rep_name=lead_dict.get("assigned_to_name") or "Rep",
                    allocated_by=lead_dict.get("allocated_by") or "system",
                    db=session,
                )
            elif trigger == "hot_lead":
                notify_hot_lead(lead_dict, db=session)
        finally:
            session.close()
    except Exception:
        import logging
        logging.getLogger("crm.leads").exception(f"Notification dispatch failed for {lead_id}")
router = APIRouter()


def _lead_to_response(lead: Lead) -> LeadResponse:
    return LeadResponse(
        id=lead.id,
        client_id=lead.client_id,
        campaign_id=lead.campaign_id,
        source=lead.source.value if isinstance(lead.source, LeadSource) else lead.source,
        source_query=lead.source_query,
        source_detail=lead.source_detail,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        location=lead.location,
        address=lead.address,
        status=lead.status.value if isinstance(lead.status, LeadStatus) else lead.status,
        lead_type=lead.lead_type.value if isinstance(lead.lead_type, LeadType) else lead.lead_type,
        quality_score=lead.quality_score,
        contact_name=lead.contact_name,
        contact_email=lead.contact_email,
        contact_phone=lead.contact_phone,
        company_name=lead.company_name,
        company_website=lead.company_website,
        message_excerpt=lead.message_excerpt,
        pitch_sent=lead.pitch_sent,
        sent_to_client_at=lead.sent_to_client_at,
        client_response=lead.client_response,
        conversion_status=lead.conversion_status,
        converted_at=lead.converted_at,
        quote_amount=lead.quote_amount,
        estimated_deal_value=lead.estimated_deal_value,
        created_by=lead.created_by,
        payment_status=lead.payment_status,
        notes=lead.notes,
        archived=lead.archived,
        archived_at=lead.archived_at,
        assigned_to=lead.assigned_to,
        assigned_to_name=lead.assigned_to_name,
        assigned_at=lead.assigned_at,
        last_follow_up_at=lead.last_follow_up_at,
        follow_up_count=lead.follow_up_count,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


@router.post("", response_model=LeadResponse, status_code=201)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Create a new lead. Called by RankBuilder agents (service token) or admins."""
    # Enforce client scope — agents/admins can only write to their own client
    # (SYSTEM_ADMIN may write to any; CLIENT_ADMIN forced to own client)
    effective_client_id = enforce_client_scope(payload.client_id, current_user)

    # Validate source
    try:
        source_val = LeadSource(payload.source)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {payload.source}. Must be one of: {[e.value for e in LeadSource]}",
        )

    # Validate lead_type if provided
    lead_type_val = None
    if payload.lead_type:
        try:
            lead_type_val = LeadType(payload.lead_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid lead_type: {payload.lead_type}. Must be VALID, INVALID, or FOLLOW_UP.",
            )

    # ── Deduplication check ────────────────────────────────────────────────
    existing = find_duplicate(
        db, effective_client_id, payload.contact_email, payload.contact_phone
    )
    if existing:
        # Merge new info into the existing lead instead of creating a duplicate
        new_fields = {
            "contact_name": payload.contact_name,
            "contact_phone": payload.contact_phone,
            "company_name": payload.company_name,
            "company_website": payload.company_website,
            "location": payload.location,
            "message_excerpt": payload.message_excerpt,
            "pitch_sent": payload.pitch_sent,
            "notes": payload.notes,
        }
        lead, _ = merge_duplicate(db, existing, new_fields, source="system")
        # Record that a duplicate was attempted
        hist = LeadHistory(
            lead_id=existing.id,
            field_changed="duplicate_attempt",
            old_value=None,
            new_value=f"Duplicate lead from {source_val.value} merged into existing",
            changed_by="system",
        )
        db.add(hist)
        db.commit()
        return _lead_to_response(lead)

    lead = Lead(
        client_id=effective_client_id,
        campaign_id=payload.campaign_id,
        source=source_val,
        source_query=payload.source_query,
        source_detail=payload.source_detail,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        location=payload.location,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        company_name=payload.company_name,
        company_website=payload.company_website,
        message_excerpt=payload.message_excerpt,
        pitch_sent=payload.pitch_sent,
        quality_score=payload.quality_score,
        quote_amount=payload.quote_amount,
        estimated_deal_value=payload.estimated_deal_value,
        payment_status=payload.payment_status,
        created_by=current_user.email if current_user else None,
        lead_type=lead_type_val,
        notes=payload.notes,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Auto-compute quality score from scoring rules
    lead.quality_score = compute_score(lead, db)
    db.commit()
    db.refresh(lead)

    # Record creation in history
    history = LeadHistory(
        lead_id=lead.id,
        field_changed="created",
        old_value=None,
        new_value=f"Lead created from {source_val.value}",
        changed_by="system",
    )
    db.add(history)

    # ── Manual UI create → assign to the person who created it ─────────────
    # (Automatic incoming leads are region-routed in the public endpoint.)
    if current_user:
        lead.assigned_to = current_user.email
        lead.assigned_to_name = current_user.full_name or current_user.email
        lead.assigned_at = datetime.utcnow()
    db.commit()

    # ── Email notifications (background) ─────────────────────────────────────
    _executor.submit(_notify_async, "new_lead", lead.id, db)
    if lead.assigned_to:
        # Tell the rep this lead is now theirs (region auto-routing)
        _executor.submit(_notify_async, "lead_allocated", lead.id, db)
    if (lead.quality_score or 0) >= 70:
        # High-intent lead — fire urgent hot-lead alert
        _executor.submit(_notify_async, "hot_lead", lead.id, db)

    return _lead_to_response(lead)


@router.get("", response_model=LeadListResponse)
def list_leads(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    status: Optional[str] = Query(None, description="Filter by status"),
    lead_type: Optional[str] = Query(None, description="Filter by lead type: VALID/INVALID/FOLLOW_UP"),
    quality_score: Optional[int] = Query(None, ge=0, le=100, description="Filter by quality score (0-100)"),
    source: Optional[str] = Query(None, description="Filter by source"),
    search: Optional[str] = Query(None, description="Search by company name or email"),
    contact_email: Optional[str] = Query(None, description="Lookup by exact email"),
    include_archived: bool = Query(False, description="Include archived leads"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List leads with optional filters. Scoped to the authenticated user's client."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)

    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    if current_user.role == UserRole.AGENT:
        # Sales agents see leads assigned to them OR leads they created
        from sqlalchemy import or_
        q = q.filter(or_(Lead.assigned_to == current_user.email, Lead.created_by == current_user.email))
    if campaign_id:
        q = q.filter(Lead.campaign_id == campaign_id)
    if status:
        try:
            status_enum = LeadStatus(status)
            q = q.filter(Lead.status == status_enum)
        except ValueError:
            pass  # Ignore invalid filter
    if lead_type:
        try:
            type_enum = LeadType(lead_type)
            q = q.filter(Lead.lead_type == type_enum)
        except ValueError:
            pass
    if source:
        try:
            source_enum = LeadSource(source)
            q = q.filter(Lead.source == source_enum)
        except ValueError:
            pass
    if quality_score:
        q = q.filter(Lead.quality_score == quality_score)
    if search:
        search_term = f"%{search}%"
        q = q.filter(
            (Lead.company_name.ilike(search_term)) |
            (Lead.contact_email.ilike(search_term)) |
            (Lead.contact_name.ilike(search_term))
        )

    if not include_archived:
        q = q.filter(Lead.archived == 0)

    total = q.count()
    leads = q.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()

    return LeadListResponse(total=total, leads=[_lead_to_response(l) for l in leads])


@router.get("/export")
def export_leads(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    status: Optional[str] = Query(None, description="Filter by status"),
    lead_type: Optional[str] = Query(None, description="Filter by lead type"),
    source: Optional[str] = Query(None, description="Filter by source"),
    search: Optional[str] = Query(None, description="Search by company/email/name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export leads as CSV (scoped to the authenticated user's client).
    Returns a downloadable CSV file with all matching leads.
    """
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)

    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    if current_user.role == UserRole.AGENT:
        # Sales agents see leads assigned to them OR leads they created
        from sqlalchemy import or_
        q = q.filter(or_(Lead.assigned_to == current_user.email, Lead.created_by == current_user.email))
    if campaign_id:
        q = q.filter(Lead.campaign_id == campaign_id)
    if status:
        try:
            q = q.filter(Lead.status == LeadStatus(status))
        except ValueError:
            pass
    if lead_type:
        try:
            q = q.filter(Lead.lead_type == LeadType(lead_type))
        except ValueError:
            pass
    if source:
        try:
            q = q.filter(Lead.source == LeadSource(source))
        except ValueError:
            pass
    if search:
        search_term = f"%{search}%"
        q = q.filter(
            (Lead.company_name.ilike(search_term)) |
            (Lead.contact_email.ilike(search_term)) |
            (Lead.contact_name.ilike(search_term))
        )

    leads = q.order_by(Lead.created_at.desc()).all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Created", "Source", "Source Detail", "Campaign", "Status",
        "Lead Type", "Quality", "Contact Name", "Email", "Phone",
        "Company", "Website", "Location", "UTM Source", "UTM Medium",
        "UTM Campaign", "Message", "Pitch Sent", "Sent To Client",
        "Client Response", "Conversion", "Converted At", "Notes",
    ])

    for lead in leads:
        campaign_name = lead.campaign.name if lead.campaign else ""
        writer.writerow([
            lead.id,
            lead.created_at.strftime("%Y-%m-%d %H:%M") if lead.created_at else "",
            lead.source.value if isinstance(lead.source, LeadSource) else str(lead.source or ""),
            lead.source_detail or "",
            campaign_name,
            lead.status.value if isinstance(lead.status, LeadStatus) else str(lead.status or ""),
            lead.lead_type.value if isinstance(lead.lead_type, LeadType) else str(lead.lead_type or ""),
            lead.quality_score if lead.quality_score is not None else "",
            lead.contact_name or "",
            lead.contact_email or "",
            lead.contact_phone or "",
            lead.company_name or "",
            lead.company_website or "",
            lead.location or "",
            lead.utm_source or "",
            lead.utm_medium or "",
            lead.utm_campaign or "",
            lead.message_excerpt or "",
            lead.pitch_sent or "",
            lead.sent_to_client_at.strftime("%Y-%m-%d %H:%M") if lead.sent_to_client_at else "",
            lead.client_response or "",
            lead.conversion_status or "",
            lead.converted_at.strftime("%Y-%m-%d %H:%M") if lead.converted_at else "",
            lead.notes or "",
        ])

    output.seek(0)
    filename = f"leads_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single lead by ID (scoped to user's client)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    enforce_agent_assignment(lead, current_user)
    return _lead_to_response(lead)


@router.get("/{lead_id}/history", response_model=LeadHistoryResponse)
def get_lead_history(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full audit/history trail for a lead (scoped to user's client)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    rows = (
        db.query(LeadHistory)
        .filter(LeadHistory.lead_id == lead_id)
        .order_by(LeadHistory.changed_at.asc())
        .all()
    )
    return LeadHistoryResponse(
        history=[
            LeadHistoryItem(
                id=r.id,
                lead_id=r.lead_id,
                field_changed=r.field_changed,
                old_value=r.old_value,
                new_value=r.new_value,
                changed_by=r.changed_by,
                changed_at=r.changed_at,
            )
            for r in rows
        ]
    )


@router.post("/{lead_id}/assign", response_model=LeadResponse)
def assign_lead_manual(
    lead_id: str,
    payload: LeadAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Manually reassign a lead to a specific sales rep. Logs the change.
    Admin-only: AGENTs cannot reassign leads."""
    if current_user.role == UserRole.AGENT:
        raise HTTPException(status_code=403, detail="Only admins can reassign leads.")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)

    old_rep = lead.assigned_to
    lead.assigned_to = payload.assigned_to
    lead.assigned_to_name = payload.assigned_to_name or payload.assigned_to
    lead.assigned_at = datetime.utcnow()

    hist = LeadHistory(
        lead_id=lead.id,
        field_changed="assigned_to",
        old_value=old_rep or "",
        new_value=f"{lead.assigned_to_name} <{lead.assigned_to}>",
        changed_by=current_user.email if current_user else "system",
    )
    db.add(hist)
    db.commit()
    db.refresh(lead)

    # Notify the newly-assigned rep (manual manager allocation)
    if lead.assigned_to:
        lead._allocated_by = current_user.email if current_user else "system"
        _executor.submit(_notify_async, "lead_allocated", lead.id, db)

    return _lead_to_response(lead)


@router.post("/{lead_id}/follow-up", response_model=LeadFollowUpResponse)
def log_follow_up_endpoint(
    lead_id: str,
    payload: LeadFollowUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """
    Log a follow-up action on a lead. Increments follow-up count, records the
    activity in the lead timeline for productivity tracking.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)

    who = payload.changed_by or (current_user.email if current_user else "system")
    result = log_follow_up(
        db, lead, payload.note, changed_by=who,
        activity_type=payload.activity_type,
        outcome=payload.outcome,
        occurred_at=payload.occurred_at,
    )

    # Also mark the lead as CONTACTED if it's still NEW/REVIEWED
    if lead.status in (LeadStatus.NEW, LeadStatus.REVIEWED):
        lead.status = LeadStatus.CONTACTED
        hist = LeadHistory(
            lead_id=lead.id,
            field_changed="status",
            old_value="NEW",
            new_value="CONTACTED",
            changed_by=who,
        )
        db.add(hist)
        db.commit()

    return LeadFollowUpResponse(
        lead_id=lead.id,
        follow_up_count=result["follow_up_count"],
        last_follow_up_at=lead.last_follow_up_at,
        message=f"Follow-up logged. Total follow-ups: {result['follow_up_count']}",
    )


@router.get("/{lead_id}/activities", response_model=LeadActivityResponse)
def get_lead_activities(lead_id: str, db: Session = Depends(get_db)):
    """Get the full stacked activity timeline for a lead (calls, emails, etc.).

    Every attempt is preserved as its own row — e.g. called 08:00 no answer,
    called 10:00 no answer — so the full history is visible.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    rows = (
        db.query(LeadActivity)
        .filter(LeadActivity.lead_id == lead_id)
        .order_by(LeadActivity.occurred_at.asc())
        .all()
    )
    return LeadActivityResponse(
        activities=[
            LeadActivityItem(
                id=r.id,
                lead_id=r.lead_id,
                activity_type=r.activity_type,
                outcome=r.outcome,
                note=r.note,
                occurred_at=r.occurred_at,
                created_at=r.created_at,
                created_by=r.created_by,
            )
            for r in rows
        ]
    )


@router.post("/{lead_id}/emails", response_model=EmailLogItem, status_code=201)
def log_email(
    lead_id: str,
    payload: EmailLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Attach an email to a lead's timeline (short-term manual entry).

    Phase 2 will replace this with Office 365 / Outlook Graph auto-capture.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)

    who = payload.created_by or (current_user.email if current_user else "system")
    email = EmailLog(
        lead_id=lead.id,
        direction=payload.direction,
        subject=payload.subject,
        body=payload.body,
        from_email=payload.from_email,
        to_email=payload.to_email,
        sent_at=payload.sent_at or datetime.utcnow(),
        created_by=who,
    )
    db.add(email)
    db.commit()
    db.refresh(email)

    # Also log it as an activity on the timeline
    activity = LeadActivity(
        lead_id=lead.id,
        activity_type="EMAIL",
        outcome="SENT" if payload.direction == "OUTBOUND" else "RECEIVED",
        note=f"Email {payload.direction.lower()}: {payload.subject or '(no subject)'}",
        occurred_at=email.sent_at,
        created_by=who,
    )
    db.add(activity)
    db.commit()

    return EmailLogItem(
        id=email.id,
        lead_id=email.lead_id,
        direction=email.direction,
        subject=email.subject,
        body=email.body,
        from_email=email.from_email,
        to_email=email.to_email,
        sent_at=email.sent_at,
        created_at=email.created_at,
        created_by=email.created_by,
    )


@router.get("/{lead_id}/emails", response_model=EmailLogResponse)
def get_lead_emails(lead_id: str, db: Session = Depends(get_db)):
    """Get the email log for a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    rows = (
        db.query(EmailLog)
        .filter(EmailLog.lead_id == lead_id)
        .order_by(EmailLog.sent_at.asc())
        .all()
    )
    return EmailLogResponse(
        emails=[
            EmailLogItem(
                id=r.id,
                lead_id=r.lead_id,
                direction=r.direction,
                subject=r.subject,
                body=r.body,
                from_email=r.from_email,
                to_email=r.to_email,
                sent_at=r.sent_at,
                created_at=r.created_at,
                created_by=r.created_by,
                notification_type=r.notification_type,
                status=r.status,
                message_id=r.message_id,
            )
            for r in rows
        ]
    )


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Update lead fields. Records all changes in lead history."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    enforce_agent_assignment(lead, current_user)

    changes = []

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        old_val = getattr(lead, field)
        setattr(lead, field, value)
        changes.append((field, str(old_val), str(value)))

        # Track sent_to_client timestamp
        if field == "status" and value == "SENT" and not lead.sent_to_client_at:
            lead.sent_to_client_at = datetime.utcnow()
            # Fire notification in background — pitch was sent to journalist/editor
            _executor.submit(_notify_async, "lead_sent", lead.id, db)

        # Track conversion
        if field == "conversion_status" and value == "CONVERTED":
            lead.converted_at = datetime.utcnow()

    if changes:
        lead.updated_at = datetime.utcnow()
        for field, old_val, new_val in changes:
            hist = LeadHistory(
                lead_id=lead.id,
                field_changed=field,
                old_value=old_val,
                new_value=new_val,
                changed_by="system",
            )
            db.add(hist)

    # Recompute quality score from scoring rules (fields may have changed)
    lead.quality_score = compute_score(lead, db)

    db.commit()
    db.refresh(lead)
    return _lead_to_response(lead)


@router.post("/{lead_id}/archive", response_model=LeadResponse)
def archive_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Archive a lead (soft delete — hides it but keeps data for reporting)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    lead.archived = 1
    lead.archived_at = datetime.utcnow()
    db.add(LeadHistory(lead_id=lead.id, field_changed="archived",
                       new_value="1", changed_by=current_user.email))
    db.commit()
    db.refresh(lead)
    return _lead_to_response(lead)


@router.post("/{lead_id}/restore", response_model=LeadResponse)
def restore_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Restore an archived lead back to the active list."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    lead.archived = 0
    lead.archived_at = None
    db.add(LeadHistory(lead_id=lead.id, field_changed="archived",
                       old_value="1", new_value="0", changed_by=current_user.email))
    db.commit()
    db.refresh(lead)
    return _lead_to_response(lead)


@router.delete("/{lead_id}", status_code=204)
def delete_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Delete a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    db.delete(lead)
    db.commit()
