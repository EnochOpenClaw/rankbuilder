"""
RankBuilder CRM — Clients API Route
POST /api/clients          — Create client
GET  /api/clients          — List all clients
GET  /api/clients/{id}    — Get client
PATCH /api/clients/{id}   — Update client
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db, Client, User
from backend.schemas import ClientCreate, ClientResponse
from backend.routes.auth import get_current_user, require_admin_or_owner

router = APIRouter()


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
