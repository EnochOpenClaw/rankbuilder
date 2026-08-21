"""
RankBuilder CRM — Lead Reminders API
User-scheduled reminders on a lead. When remind_at arrives, the cron
(scripts/lead_reminders.py) sends a notification and marks it SENT.

POST   /api/leads/{lead_id}/reminders            — Schedule a reminder
GET    /api/leads/{lead_id}/reminders            — List reminders for a lead
POST   /api/leads/{lead_id}/reminders/{rid}/dismiss — Dismiss a reminder
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, Lead, LeadReminder, User
from backend.routes.auth import (
    get_current_user,
    require_admin_or_owner,
    enforce_client_scope,
    enforce_agent_assignment,
)

router = APIRouter()


class ReminderCreate(BaseModel):
    remind_at: datetime
    note: Optional[str] = None


class ReminderItem(BaseModel):
    id: str
    lead_id: str
    remind_at: datetime
    note: Optional[str] = None
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReminderListResponse(BaseModel):
    reminders: list[ReminderItem]


def _reminder_to_item(r: LeadReminder) -> ReminderItem:
    return ReminderItem(
        id=r.id,
        lead_id=r.lead_id,
        remind_at=r.remind_at,
        note=r.note,
        status=r.status,
        created_by=r.created_by,
        created_at=r.created_at,
        sent_at=r.sent_at,
    )


def _get_lead(lead_id: str, db: Session, current_user: User) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    enforce_agent_assignment(lead, current_user)
    return lead


@router.post("/{lead_id}/reminders", response_model=ReminderItem, status_code=201)
def create_reminder(
    lead_id: str,
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Schedule a reminder on a lead."""
    lead = _get_lead(lead_id, db, current_user)
    # Normalize aware datetime (frontend sends ISO with Z/timezone) to naive UTC
    remind = payload.remind_at
    if remind.tzinfo is not None:
        remind = remind.astimezone(timezone.utc).replace(tzinfo=None)
    if remind <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reminder time must be in the future.")
    r = LeadReminder(
        lead_id=lead.id,
        remind_at=payload.remind_at,
        note=payload.note,
        status="PENDING",
        created_by=current_user.email if current_user else None,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _reminder_to_item(r)


@router.get("/{lead_id}/reminders", response_model=ReminderListResponse)
def list_reminders(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List reminders for a lead (newest first)."""
    lead = _get_lead(lead_id, db, current_user)
    rows = (
        db.query(LeadReminder)
        .filter(LeadReminder.lead_id == lead.id)
        .order_by(LeadReminder.remind_at.desc())
        .all()
    )
    return ReminderListResponse(reminders=[_reminder_to_item(r) for r in rows])


@router.post("/{lead_id}/reminders/{reminder_id}/dismiss", response_model=ReminderItem)
def dismiss_reminder(
    lead_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Dismiss a reminder (mark as DISMISSED so it won't fire)."""
    lead = _get_lead(lead_id, db, current_user)
    r = (
        db.query(LeadReminder)
        .filter(LeadReminder.id == reminder_id, LeadReminder.lead_id == lead.id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    r.status = "DISMISSED"
    db.commit()
    db.refresh(r)
    return _reminder_to_item(r)
