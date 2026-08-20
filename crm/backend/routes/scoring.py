"""
RankBuilder CRM — Scoring Rules API
GET    /api/scoring/rules          — List rules (SYSTEM_ADMIN: all; others: their client's + global)
POST   /api/scoring/rules          — Create a rule (SYSTEM_ADMIN only)
PATCH  /api/scoring/rules/{id}     — Update a rule (SYSTEM_ADMIN only)
DELETE /api/scoring/rules/{id}     — Deactivate a rule (SYSTEM_ADMIN only)
GET    /api/scoring/tiers          — Return tier thresholds + current lead tier distribution
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db, ScoringRule, User, Lead
from backend.routes.auth import get_current_user
from backend.scoring import score_tier

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    field: str = Field(..., description="source, has_phone, has_website, has_email, no_email, lead_type, location, message_keyword, age_days")
    operator: str = Field("eq", description="eq, ne, contains, is_true, is_false, gt, lt")
    value: Optional[str] = None
    points: int = Field(..., description="Points to add (positive) or subtract (negative)")
    client_id: Optional[str] = None  # NULL = global rule


class RuleUpdate(BaseModel):
    field: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    points: Optional[int] = None
    is_active: Optional[int] = None


class RuleResponse(BaseModel):
    id: str
    client_id: Optional[str]
    field: str
    operator: str
    value: Optional[str]
    points: int
    is_active: int
    created_at: datetime = None

    class Config:
        from_attributes = True


class TierResponse(BaseModel):
    hot: int
    warm: int
    cold: int
    thresholds: dict


def _require_system_admin(current_user: User):
    if current_user.role.value != "SYSTEM_ADMIN":
        raise HTTPException(status_code=403, detail="Only SYSTEM_ADMIN can manage scoring rules")
    return current_user


@router.get("/rules", response_model=list[RuleResponse])
def list_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List scoring rules. SYSTEM_ADMIN sees all; others see global + their client's."""
    q = db.query(ScoringRule)
    if current_user.role.value != "SYSTEM_ADMIN":
        q = q.filter(
            (ScoringRule.client_id.is_(None)) |
            (ScoringRule.client_id == current_user.client_id)
        )
    return q.order_by(ScoringRule.points.desc()).all()


@router.post("/rules", response_model=RuleResponse, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a scoring rule — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    rule = ScoringRule(
        id=str(uuid.uuid4()),
        client_id=payload.client_id,
        field=payload.field,
        operator=payload.operator,
        value=payload.value,
        points=payload.points,
        is_active=1,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a scoring rule — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    rule = db.query(ScoringRule).filter(ScoringRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", response_model=RuleResponse)
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a scoring rule (soft delete) — SYSTEM_ADMIN only."""
    _require_system_admin(current_user)
    rule = db.query(ScoringRule).filter(ScoringRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = 0
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/tiers", response_model=TierResponse)
def get_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return tier thresholds + current lead distribution by tier."""
    from backend.scoring import compute_score

    # Load all leads for the user's scope
    q = db.query(Lead)
    if current_user.role.value != "SYSTEM_ADMIN":
        if not current_user.client_id:
            raise HTTPException(status_code=403, detail="Account not linked to a client")
        q = q.filter(Lead.client_id == current_user.client_id)

    hot = warm = cold = 0
    for lead in q.all():
        tier = score_tier(compute_score(lead, db))
        if tier == "HOT":
            hot += 1
        elif tier == "WARM":
            warm += 1
        else:
            cold += 1

    return TierResponse(
        hot=hot,
        warm=warm,
        cold=cold,
        thresholds={"hot": 70, "warm": 40, "cold": 0},
    )
