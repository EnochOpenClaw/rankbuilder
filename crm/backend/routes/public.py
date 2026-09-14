"""
RankBuilder CRM — Public Lead Capture Routes
POST /api/leads/public — capture a lead from website / Facebook / call centre
                              (no auth, uses X-API-Key header)
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db, Client
from backend.schemas import LeadPublicCreate, LeadPublicResponse
from backend.routes.leads import _executor, _notify_async
from backend.lead_capture import capture_lead as _run_capture

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

    # Run the shared capture pipeline (dedupe → merge/create → history → assign)
    result, created = _run_capture(
        db,
        client,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        company_name=payload.company_name,
        product_interest=payload.product_interest,
        location=payload.location,
        message=payload.message,
        source=payload.source,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        dedupe_history_note="Duplicate lead from public form merged into existing",
    )

    # ── Email notification: new lead alert ──────────────────────────────────
    # Only fire for freshly-created leads (merged duplicates returned before the
    # notification historically, so we preserve that behavior).
    if created and result.lead_id:
        _executor.submit(_notify_async, "new_lead", result.lead_id, db)

    return result
