"""
RankBuilder CRM — Public Lead Capture Routes
POST /api/leads/public — capture a lead from website / Facebook / call centre
                              (no auth, uses X-API-Key header)
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db, Client, Lead, LeadHistory, LeadSource, LeadStatus
from backend.schemas import LeadPublicCreate, LeadPublicResponse
from backend.routes.leads import _executor, _notify_async
from backend.dedupe import find_duplicate, merge_duplicate

router = APIRouter()


@router.post("/leads/public", response_model=LeadPublicResponse, status_code=201)
def capture_lead(
    payload: LeadPublicCreate,
    x_api_key: str = Header(..., description="Client API key"),
    db: Session = Depends(get_db),
):
    """
    Public lead capture endpoint.
    Auth: X-API-Key header with the client's API token.
    Sources: WEBSITE, FACEBOOK, DIRECT_MAIL, CALL_IN, MANUAL
    """
    # Validate API key
    client = db.query(Client).filter(Client.api_key == x_api_key).first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Map source_detail roughly to a source type if it's recognizable
    detail_lower = (payload.product_interest or "").lower()
    source = LeadSource.WEBSITE  # default

    # ── Deduplication check ────────────────────────────────────────────────
    existing = find_duplicate(db, client.id, payload.contact_email, payload.contact_phone)
    if existing:
        new_fields = {
            "contact_name": payload.contact_name,
            "contact_phone": payload.contact_phone,
            "company_name": payload.company_name,
            "location": payload.location,
            "message_excerpt": payload.message,
            "source_detail": payload.product_interest or "Direct enquiry",
        }
        lead, _ = merge_duplicate(db, existing, new_fields, source="public_form")
        hist = LeadHistory(
            lead_id=existing.id,
            field_changed="duplicate_attempt",
            old_value=None,
            new_value="Duplicate lead from public form merged into existing",
            changed_by="system",
        )
        db.add(hist)
        db.commit()
        return LeadPublicResponse(
            success=True,
            lead_id=existing.id,
            message="Lead already exists — merged new info into existing lead.",
        )

    # Build the lead
    lead = Lead(
        client_id=client.id,
        source=source,
        source_detail=payload.product_interest or "Direct enquiry",
        location=payload.location,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        company_name=payload.company_name,
        message_excerpt=payload.message,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
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
        new_value=f"Lead captured via public form",
        changed_by="system",
    )
    db.add(history)
    db.commit()

    # ── Email notification: new lead alert ──────────────────────────────────
    # Match the authenticated route: fire notification in background thread
    _executor.submit(_notify_async, "new_lead", lead.id, db)

    return LeadPublicResponse(
        success=True,
        lead_id=lead.id,
        message="Lead captured. We'll be in touch shortly!",
    )
