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

from backend.database import get_db, NotificationSetting, NotificationGroup, User
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


# ── Notification Groups ────────────────────────────────────────────────────────

class NotificationGroupCreate(BaseModel):
    """Create a named notification group (e.g. 'Sales Team') with members."""
    name: str
    description: str = ""
    client_id: Optional[str] = None  # Required for SYSTEM_ADMIN, auto for CLIENT_ADMIN
    members: list[dict] = []  # [{target, name, notification_type}]


class NotificationGroupResponse(BaseModel):
    id: str
    client_id: str
    name: str
    description: str | None
    members: list[dict] = []

    class Config:
        from_attributes = True


@router.get("/groups", response_model=list[NotificationGroupResponse])
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notification groups for the current client's company."""
    if current_user.role.value == "SYSTEM_ADMIN":
        groups = db.query(NotificationGroup).order_by(NotificationGroup.name).all()
    else:
        groups = db.query(NotificationGroup).filter(
            NotificationGroup.client_id == current_user.client_id
        ).order_by(NotificationGroup.name).all()

    result = []
    for g in groups:
        members = [
            {"id": m.id, "target": m.target, "name": m.name, "notification_type": m.notification_type, "enabled": m.enabled}
            for m in g.members if m.enabled
        ]
        result.append(NotificationGroupResponse(
            id=g.id, client_id=g.client_id, name=g.name, description=g.description, members=members
        ))
    return result


@router.post("/groups", response_model=NotificationGroupResponse, status_code=201)
def create_group(
    payload: NotificationGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a notification group with members."""
    client_id = _require_client_admin(db, current_user)
    if client_id is None:
        if not payload.client_id:
            raise HTTPException(status_code=400, detail="client_id required in payload for system admin")
        client_id = payload.client_id

    group = NotificationGroup(
        client_id=client_id,
        name=payload.name,
        description=payload.description or None,
    )
    db.add(group)
    db.flush()  # get group.id

    for m in payload.members:
        ntype = m.get("notification_type", "EMAIL")
        target = m.get("target", "")
        if ntype == "EMAIL" and "@" not in target:
            raise HTTPException(status_code=400, detail=f"Invalid email: {target}")
        setting = NotificationSetting(
            client_id=client_id,
            group_id=group.id,
            notification_type=ntype,
            target=target,
            name=m.get("name", ""),
            enabled=True,
        )
        db.add(setting)

    db.commit()
    db.refresh(group)

    members = [
        {"id": m.id, "target": m.target, "name": m.name, "notification_type": m.notification_type, "enabled": m.enabled}
        for m in group.members if m.enabled
    ]
    return NotificationGroupResponse(
        id=group.id, client_id=group.client_id, name=group.name, description=group.description, members=members
    )


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a notification group and its members."""
    group = db.query(NotificationGroup).filter(NotificationGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if current_user.role.value != "SYSTEM_ADMIN" and group.client_id != current_user.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(group)
    db.commit()
