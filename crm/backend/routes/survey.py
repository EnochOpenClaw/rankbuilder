"""
RankBuilder CRM — SEO Survey Lead Capture Route
POST /api/survey/submit — anonymous survey lead capture
                              (no external auth; the client is resolved server-side,
                               so the client API key is NEVER exposed in page code)
"""

import time
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from backend.database import get_db, Client
from backend.lead_capture import capture_lead
from backend.routes.leads import _executor, _notify_async

router = APIRouter()


# ── Survey schema ──────────────────────────────────────────────────────────────
class SurveySubmit(BaseModel):
    """Payload from the SEO survey landing page (linkable-asset lead capture)."""
    contact_name: str
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None  # optional
    suburb: Optional[str] = None  # location / suburb
    answers: dict = Field(default_factory=dict)  # question id -> chosen value
    # UTM attribution (captured from the page URL query string)
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

    @field_validator("contact_email", mode="before")
    @classmethod
    def _empty_email_to_none(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    class Config:
        use_enum_values = True


# ── Light in-process rate limit (per client IP, sliding window) ────────────────
_RATE_LIMIT_WINDOW = 5.0       # seconds
_RATE_LIMIT_MAX = 5            # max submissions per window
_rate_lock = Lock()
_rate_buckets: dict[str, list] = {}  # ip -> [timestamps]


def _rate_limited(ip: str) -> bool:
    """Return True when the IP has exceeded the window budget (reject)."""
    now = time.monotonic()
    with _rate_lock:
        stamps = [t for t in _rate_buckets.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
        if len(stamps) >= _RATE_LIMIT_MAX:
            _rate_buckets[ip] = stamps
            return True
        stamps.append(now)
        _rate_buckets[ip] = stamps
        # Opportunistic cleanup so the dict doesn't grow unbounded
        if len(_rate_buckets) > 10_000:
            _rate_buckets.clear()
        return False


def _resolve_default_client(db: Session) -> Client:
    """Resolve the default client server-side (House of Supreme, else first)."""
    client = (
        db.query(Client)
        .filter(Client.company_name == "House of Supreme")
        .first()
    )
    if not client:
        client = db.query(Client).order_by(Client.created_at.asc()).first()
    return client


def _build_source_detail(answers: dict) -> str:
    """
    Build a short human-readable survey summary from the answers, e.g.
        "SEO Survey: shutters-vs-bars — concern=heat, windows=aluminium"
    """
    parts = []
    for key, value in answers.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    summary = ", ".join(parts) if parts else "no answers provided"
    return f"SEO Survey: shutters-vs-bars — {summary}"


@router.post("/survey/submit", status_code=201)
def submit_survey(
    payload: SurveySubmit,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Anonymous survey lead capture for the SEO linkable asset.

    No external auth: the default client is resolved server-side so the client's
    API key never reaches the browser. Reuses the same dedupe → merge/create →
    history → auto-assign → notify pipeline as /api/leads/public.
    """
    # Light per-IP rate limit
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many submissions — please wait a moment and try again.",
        )

    client = _resolve_default_client(db)
    if not client:
        raise HTTPException(status_code=503, detail="No client configured for survey capture.")

    source_detail = _build_source_detail(payload.answers)

    result, created = capture_lead(
        db,
        client,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        company_name=None,
        product_interest=source_detail,  # survey summary as the lead's product_interest
        location=payload.suburb,
        message=None,
        source="WEBSITE",
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        dedupe_history_note="Duplicate survey submission merged into existing lead",
    )

    # Fire the new-lead alert only for freshly-created leads
    if created and result.lead_id:
        _executor.submit(_notify_async, "new_lead", result.lead_id, db)

    return result
