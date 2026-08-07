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

from backend.database import get_db, Lead, LeadHistory, LeadSource, LeadStatus, LeadType
from backend.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListResponse,
    LeadHistoryItem,
    LeadHistoryResponse,
)
from backend.notifications import notify_new_lead, notify_lead_sent
from backend.dedupe import find_duplicate, merge_duplicate
from backend.routes.auth import (
    get_current_user,
    require_admin_or_owner,
    enforce_client_scope,
)
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
            }
            if trigger == "new_lead":
                notify_new_lead(lead_dict, db=session)
            elif trigger == "lead_sent":
                notify_lead_sent(lead_dict, db=session)
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
        notes=lead.notes,
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
        lead_type=lead_type_val,
        notes=payload.notes,
        status=LeadStatus.NEW,
    )
    db.add(lead)
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
    db.commit()

    # ── Email notification: new lead alert ──────────────────────────────────
    _executor.submit(_notify_async, "new_lead", lead.id, db)

    return _lead_to_response(lead)


@router.get("", response_model=LeadListResponse)
def list_leads(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    status: Optional[str] = Query(None, description="Filter by status"),
    lead_type: Optional[str] = Query(None, description="Filter by lead type: VALID/INVALID/FOLLOW_UP"),
    source: Optional[str] = Query(None, description="Filter by source"),
    search: Optional[str] = Query(None, description="Search by company name or email"),
    contact_email: Optional[str] = Query(None, description="Lookup by exact email"),
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
    if search:
        search_term = f"%{search}%"
        q = q.filter(
            (Lead.company_name.ilike(search_term)) |
            (Lead.contact_email.ilike(search_term)) |
            (Lead.contact_name.ilike(search_term))
        )

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
