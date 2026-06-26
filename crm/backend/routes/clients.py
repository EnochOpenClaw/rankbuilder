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

from backend.database import get_db, Client
from backend.schemas import ClientCreate, ClientResponse

router = APIRouter()


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    """Register a new client in the CRM."""
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
def list_clients(db: Session = Depends(get_db)):
    """List all clients."""
    clients = db.query(Client).order_by(Client.created_at.desc()).all()
    return clients


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(client_id: str, db: Session = Depends(get_db)):
    """Get a single client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(client_id: str, payload: ClientCreate, db: Session = Depends(get_db)):
    """Update client details."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    client.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(client)
    return client
