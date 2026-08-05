"""
RankBuilder CRM — Notification Settings API
GET    /api/notifications/settings         — List notification settings for current client
POST   /api/notifications/settings         — Add a notification recipient
PATCH  /api/notifications/settings/{id}  — Update a setting (enable/disable/target)
DELETE /api/notifications/settings/{id}  — Remove a recipient
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import get_db, NotificationSetting, User
from backend.routes.auth import get_current_user

router = APIRouter()


class NotificationSettingCreate(BaseModel):
    notification_type: str = "EMAIL"
    target: str
    name: str = ""
    client_id: Optional[str] = None  # Required for SYSTEM_ADMIN, auto-used for CLIENT_ADMIN


class NotificationSettingUpdate(BaseModel):
    target: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = None


class NotificationSettingResponse(BaseModel):
    id: str
    client_id: str
    notification_type: str
    target: str | None
    name: str | None
    enabled: bool

    class Config:
        from_attributes = True


def _require_client_admin(db: Session, user: User):
    """Ensure user is SYSTEM_ADMIN or CLIENT_ADMIN. Returns client_id (or None for SYSTEM_ADMIN)."""
    if user.role.value == "SYSTEM_ADMIN":
        return None  # Caller must provide client_id in payload
    if user.role.value == "CLIENT_ADMIN":
        return user.client_id
    raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/settings", response_model=list[NotificationSettingResponse])
def list_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notification settings for the current client's company."""
    if current_user.role.value == "SYSTEM_ADMIN":
        return db.query(NotificationSetting).order_by(NotificationSetting.created_at).all()

    settings = db.query(NotificationSetting).filter(
        NotificationSetting.client_id == current_user.client_id
    ).order_by(NotificationSetting.created_at).all()
    return settings


@router.post("/settings", response_model=NotificationSettingResponse, status_code=201)
def add_setting(
    payload: NotificationSettingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a new notification recipient for the current client's company."""
    # Resolve client_id
    client_id = _require_client_admin(db, current_user)
    if client_id is None:
        # SYSTEM_ADMIN must provide client_id in payload
        if not payload.client_id:
            raise HTTPException(
                status_code=400,
                detail="client_id required in payload for system admin",
            )
        client_id = payload.client_id

    if payload.notification_type not in ("EMAIL", "SMS", "WEBHOOK"):
        raise HTTPException(status_code=400, detail="Type must be EMAIL, SMS, or WEBHOOK")

    if payload.notification_type == "EMAIL":
        if "@" not in (payload.target or ""):
            raise HTTPException(status_code=400, detail="Invalid email address")

    setting = NotificationSetting(
        client_id=client_id,
        notification_type=payload.notification_type,
        target=payload.target,
        name=payload.name or "",
        enabled=True,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


@router.patch("/settings/{setting_id}", response_model=NotificationSettingResponse)
def update_setting(
    setting_id: str,
    payload: NotificationSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a notification recipient (enable/disable/change target)."""
    setting = db.query(NotificationSetting).filter(NotificationSetting.id == setting_id).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    # Role check
    if current_user.role.value != "SYSTEM_ADMIN" and setting.client_id != current_user.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if payload.target is not None:
        setting.target = payload.target
    if payload.name is not None:
        setting.name = payload.name
    if payload.enabled is not None:
        setting.enabled = payload.enabled

    db.commit()
    db.refresh(setting)
    return setting


@router.delete("/settings/{setting_id}", status_code=204)
def delete_setting(
    setting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a notification recipient."""
    setting = db.query(NotificationSetting).filter(NotificationSetting.id == setting_id).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    if current_user.role.value != "SYSTEM_ADMIN" and setting.client_id != current_user.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(setting)
    db.commit()
