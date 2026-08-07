"""
RankBuilder CRM — Clients API Route
POST /api/clients          — Create client
POST /api/clients/onboard  — Full client onboarding (client + admin + API key + campaign)
GET  /api/clients          — List all clients
GET  /api/clients/{id}    — Get client
PATCH /api/clients/{id}   — Update client
"""

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import (
    get_db, Client, User, Campaign, UserRole, NotificationChannel,
    LeadSource, CampaignStatus,
)
from backend.schemas import (
    ClientCreate, ClientResponse, ClientOnboardRequest, ClientOnboardResponse,
)
from backend.routes.auth import get_current_user, require_admin_or_owner, hash_password

router = APIRouter()


def _generate_api_key() -> str:
    """Generate a unique 32-char hex API key."""
    return secrets.token_hex(16)


@router.post("/onboard", response_model=ClientOnboardResponse, status_code=201)
def onboard_client(
    payload: ClientOnboardRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_owner()),
):
    """
    Full client onboarding — provisions everything a new client needs:
      1. Client record (with auto-generated API key)
      2. Admin user (CLIENT_ADMIN role) for the client portal
      3. Default campaign
    Returns all credentials for handover.
    """
    # Validate admin email uniqueness
    existing_user = db.query(User).filter(User.email == payload.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already in use")

    # 1. Create client with API key
    api_key = _generate_api_key()
    client = Client(
        company_name=payload.company_name,
        contact_email=payload.contact_email,
        api_key=api_key,
        notification_channel=NotificationChannel(payload.notification_channel),
        notification_target=payload.notification_target or payload.contact_email,
    )
    db.add(client)
    db.flush()  # get client.id without committing yet

    # 2. Create admin user
    admin = User(
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_full_name or payload.company_name,
        client_id=client.id,
        role=UserRole.CLIENT_ADMIN,
        is_active=1,
    )
    db.add(admin)

    # 3. Create default campaign
    campaign = Campaign(
        client_id=client.id,
        name=payload.campaign_name or f"{payload.company_name}-Q3-Outreach",
        channel=LeadSource.GUEST_OUTREACH,
        status=CampaignStatus.ACTIVE,
    )
    db.add(campaign)

    db.commit()
    db.refresh(client)
    db.refresh(admin)
    db.refresh(campaign)

    return ClientOnboardResponse(
        client=ClientResponse(
            id=client.id,
            company_name=client.company_name,
            contact_email=client.contact_email,
            notification_channel=client.notification_channel.value if hasattr(client.notification_channel, "value") else str(client.notification_channel),
            notification_target=client.notification_target,
            api_key=client.api_key,
            created_at=client.created_at,
        ),
        api_key=api_key,
        admin_user={
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role.value if hasattr(admin.role, "value") else str(admin.role),
        },
        admin_password=payload.admin_password,
        campaign={
            "id": campaign.id,
            "name": campaign.name,
            "channel": campaign.channel.value if hasattr(campaign.channel, "value") else str(campaign.channel),
        },
    )


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_owner()),
):
    """Register a new client in the CRM (admin only)."""
    client = Client(
        company_name=payload.company_name,
        contact_email=payload.contact_email,
        notification_channel=payload.notification_channel,
        notification_target=payload.notification_target,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("", response_model=list[ClientResponse])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List clients.
    - SYSTEM_ADMIN: all clients
    - CLIENT_ADMIN / VIEWER: only their own client
    """
    q = db.query(Client)
    if current_user.role.value != "SYSTEM_ADMIN":
        if not current_user.client_id:
            raise HTTPException(status_code=403, detail="Account not linked to a client")
        q = q.filter(Client.id == current_user.client_id)
    clients = q.order_by(Client.created_at.desc()).all()
    return clients


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single client (scoped to user's client unless SYSTEM_ADMIN)."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if current_user.role.value != "SYSTEM_ADMIN" and current_user.client_id != client.id:
        raise HTTPException(status_code=403, detail="You can only access your own client")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Update client details (admin only, scoped)."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if current_user.role.value != "SYSTEM_ADMIN" and current_user.client_id != client.id:
        raise HTTPException(status_code=403, detail="You can only access your own client")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    client.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(client)
    return client
