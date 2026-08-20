"""
RankBuilder CRM — Lead Source Management API
GET   /api/sources          — List active sources (any authenticated user, for dropdowns)
GET   /api/sources/all      — List all sources incl. inactive (SYSTEM_ADMIN only)
POST  /api/sources          — Create a source (SYSTEM_ADMIN only)
PATCH /api/sources/{id}     — Update source name/active/sort (SYSTEM_ADMIN only)
DELETE /api/sources/{id}    — Deactivate a source (SYSTEM_ADMIN only)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import get_db, LeadSourceModel, User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Uppercase code e.g. HARO, LINKEDIN")
    name: str = Field(..., min_length=1, max_length=100, description="Display label")
    sort_order: int = 0


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[int] = None
    sort_order: Optional[int] = None


class SourceResponse(BaseModel):
    id: str
    code: str
    name: str
    is_active: int
    sort_order: int
    created_at: datetime = None

    class Config:
        from_attributes = True


def _require_system_admin(current_user: User):
    if current_user.role.value != "SYSTEM_ADMIN":
        raise HTTPException(status_code=403, detail="Only SYSTEM_ADMIN can manage sources")
    return current_user


@router.get("", response_model=list[SourceResponse])
def list_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ACTIVE sources (for dropdowns / reports). Any authenticated user."""
    return (
        db.query(LeadSourceModel)
        .filter(LeadSourceModel.is_active == 1)
        .order_by(LeadSourceModel.sort_order)
        .all()
    )


@router.get("/all", response_model=list[SourceResponse])
def list_all_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ALL sources incl. inactive — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    return (
        db.query(LeadSourceModel)
        .order_by(LeadSourceModel.sort_order)
        .all()
    )


@router.post("", response_model=SourceResponse, status_code=201)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new lead source — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    code = payload.code.strip().upper().replace(" ", "_")
    if not code:
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    existing = db.query(LeadSourceModel).filter(LeadSourceModel.code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Source '{code}' already exists")

    src = LeadSourceModel(
        id=str(uuid.uuid4()),
        code=code,
        name=payload.name.strip() or code,
        is_active=1,
        sort_order=payload.sort_order,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: str,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a source (rename, activate/deactivate, reorder) — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    src = db.query(LeadSourceModel).filter(LeadSourceModel.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if payload.name is not None:
        src.name = payload.name.strip() or src.name
    if payload.is_active is not None:
        src.is_active = 1 if payload.is_active else 0
    if payload.sort_order is not None:
        src.sort_order = payload.sort_order
    src.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(src)
    return src


@router.delete("/{source_id}", response_model=SourceResponse)
def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a source (soft delete) — SYSTEM_ADMIN only. Existing leads keep their source value."""
    _require_system_admin(current_user)
    src = db.query(LeadSourceModel).filter(LeadSourceModel.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    src.is_active = 0
    src.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(src)
    return src
