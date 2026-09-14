"""
RankBuilder CRM — Shared Public Lead Capture Helper
=====================================================
The public/survey lead-capture endpoints share one pipeline:

    dedupe (find_duplicate) → merge (merge_duplicate) / create → history → auto-assign → notify

Extracting it here keeps /api/leads/public and /api/survey/submit behaviourally
identical without duplicating the logic. Use capture_lead() from any public-facing
endpoint that captures a lead without an authenticated user context.
"""

from sqlalchemy.orm import Session

from backend.database import Client, Lead, LeadHistory, LeadSource, LeadStatus
from backend.schemas import LeadPublicResponse
from backend.dedupe import find_duplicate, merge_duplicate
from backend.assignment import assign_lead


def capture_lead(
    db: Session,
    client: Client,
    *,
    contact_name: str,
    contact_email=None,
    contact_phone=None,
    company_name=None,
    product_interest=None,
    location=None,
    message=None,
    source=None,
    utm_source=None,
    utm_medium=None,
    utm_campaign=None,
    dedupe_history_note="Duplicate lead merged into existing",
) -> LeadPublicResponse:
    """
    Run the full public lead-capture pipeline for a single client.

    Mirrors the historical /api/leads/public flow exactly: dedupe by email/phone,
    merge duplicates (keeping the existing lead, attaching a history entry), else
    create a NEW lead, record its creation, auto-assign to a sales rep by region,
    and fire the new-lead notification in the background.

    Returns a tuple (LeadPublicResponse, created: bool) — callers fire the
    new-lead notification only when created is True (mirrors the historical
    public route, which returned before the notification on the duplicate path).
    Everything else is committed here; the notification is dispatched via the
    leads route executor at the call site in the endpoint.
    """
    # Map source_detail roughly to a source type if it's recognizable
    # Use explicit source if provided, otherwise default to WEBSITE
    if source:
        try:
            source_val = LeadSource(source.upper())
        except ValueError:
            source_val = LeadSource.WEBSITE
    else:
        source_val = LeadSource.WEBSITE  # default

    # ── Deduplication check ────────────────────────────────────────────────
    existing = find_duplicate(db, client.id, contact_email, contact_phone)
    if existing:
        new_fields = {
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "company_name": company_name,
            "location": location,
            "message_excerpt": message,
            "source_detail": product_interest or "Direct enquiry",
        }
        lead, _ = merge_duplicate(db, existing, new_fields, source="public_form")
        hist = LeadHistory(
            lead_id=existing.id,
            field_changed="duplicate_attempt",
            old_value=None,
            new_value=dedupe_history_note,
            changed_by="system",
        )
        db.add(hist)
        db.commit()
        return LeadPublicResponse(
            success=True,
            lead_id=existing.id,
            message="Lead already exists — merged new info into existing lead.",
        ), False

    # Build the lead
    lead = Lead(
        client_id=client.id,
        source=source_val,
        source_detail=product_interest or "Direct enquiry",
        location=location,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        company_name=company_name,
        message_excerpt=message,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
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
        new_value="Lead captured via public form",
        changed_by="system",
    )
    db.add(history)
    db.commit()

    # ── Auto-assign to sales rep based on region (automatic incoming lead) ──
    assign_lead(db, lead, changed_by="system")
    db.commit()
    db.refresh(lead)

    return LeadPublicResponse(
        success=True,
        lead_id=lead.id,
        message="Lead captured. We'll be in touch shortly!",
    ), True
