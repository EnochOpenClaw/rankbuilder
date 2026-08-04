"""
RankBuilder CRM — Campaigns API Routes
POST   /api/campaigns          — Create a campaign
GET    /api/campaigns          — List campaigns (filterable by client/status/channel)
GET    /api/campaigns/{id}     — Get a single campaign with lead counts
PATCH  /api/campaigns/{id}     — Update campaign
DELETE /api/campaigns/{id}     — Delete campaign
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db, Campaign, Lead, CampaignStatus, LeadSource, LeadStatus
from backend.schemas import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
)
from backend.routes.auth import (
    get_current_user,
    require_admin_or_owner,
    enforce_client_scope,
)
from backend.database import User

router = APIRouter()


def _campaign_to_response(campaign: Campaign, db: Session) -> CampaignResponse:
    """Build a CampaignResponse including live lead counts from the DB."""
    q = db.query(Lead).filter(Lead.campaign_id == campaign.id)
    total = q.count()
    qualified = q.filter(Lead.status == LeadStatus.QUALIFIED).count()
    converted = q.filter(Lead.status == LeadStatus.CONVERTED).count()

    return CampaignResponse(
        id=campaign.id,
        client_id=campaign.client_id,
        name=campaign.name,
        channel=campaign.channel.value if isinstance(campaign.channel, LeadSource) else campaign.channel,
        status=campaign.status.value if isinstance(campaign.status, CampaignStatus) else campaign.status,
        started_at=campaign.started_at,
        ended_at=campaign.ended_at,
        lead_count=total,
        qualified_count=qualified,
        converted_count=converted,
        created_at=campaign.created_at or campaign.started_at,
    )


@router.post("", response_model=CampaignResponse, status_code=201)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Create a new campaign for a client (admin only, scoped to own client)."""
    effective_client_id = enforce_client_scope(payload.client_id, current_user)

    # Validate channel
    try:
        channel_val = LeadSource(payload.channel)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel: {payload.channel}. Must be one of: {[e.value for e in LeadSource]}",
        )

    # Validate status
    try:
        status_val = CampaignStatus(payload.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {payload.status}. Must be ACTIVE, PAUSED, or COMPLETED.",
        )

    campaign = Campaign(
        client_id=effective_client_id,
        name=payload.name,
        channel=channel_val,
        status=status_val,
        started_at=payload.started_at or datetime.utcnow(),
        ended_at=payload.ended_at,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _campaign_to_response(campaign, db)


@router.get("", response_model=CampaignListResponse)
def list_campaigns(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE/PAUSED/COMPLETED"),
    channel: Optional[str] = Query(None, description="Filter by channel/source"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List campaigns with optional filters (scoped to user's client)."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Campaign)

    if effective_client_id:
        q = q.filter(Campaign.client_id == effective_client_id)
    if status:
        try:
            q = q.filter(Campaign.status == CampaignStatus(status))
        except ValueError:
            pass
    if channel:
        try:
            q = q.filter(Campaign.channel == LeadSource(channel))
        except ValueError:
            pass

    campaigns = q.order_by(Campaign.created_at.desc()).all()
    return CampaignListResponse(
        total=len(campaigns),
        campaigns=[_campaign_to_response(c, db) for c in campaigns],
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single campaign with lead counts (scoped to user's client)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    enforce_client_scope(campaign.client_id, current_user)
    return _campaign_to_response(campaign, db)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Update campaign fields (admin only)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    enforce_client_scope(campaign.client_id, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field == "channel":
            try:
                value = LeadSource(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid channel: {value}")
        if field == "status":
            try:
                value = CampaignStatus(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {value}")
        setattr(campaign, field, value)

    db.commit()
    db.refresh(campaign)
    return _campaign_to_response(campaign, db)


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Delete a campaign (admin only). Associated leads keep their campaign_id value."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    enforce_client_scope(campaign.client_id, current_user)
    db.delete(campaign)
    db.commit()
