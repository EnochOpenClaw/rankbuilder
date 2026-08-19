"""
RankBuilder CRM — Lead Documents API
Attach files (response emails, quotes sent, etc.) to a lead.

POST   /api/leads/{lead_id}/documents            — Upload a file
GET    /api/leads/{lead_id}/documents            — List documents
GET    /api/leads/{lead_id}/documents/{doc_id}/download — Download / view a file
DELETE /api/leads/{lead_id}/documents/{doc_id}   — Delete a document
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, Lead, LeadDocument, User, UserRole
from backend.routes.auth import (
    get_current_user,
    require_admin_or_owner,
    enforce_client_scope,
    enforce_agent_assignment,
)

router = APIRouter()

# Base upload directory (outside web root; served via the download endpoint for auth)
UPLOAD_BASE = Path(os.environ.get("CRM_UPLOAD_DIR", "/root/rankbuilder/crm/uploads"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB per file

ALLOWED_CATEGORIES = {"EMAIL", "QUOTE", "RESPONSE", "OTHER"}


class DocumentItem(BaseModel):
    id: str
    lead_id: str
    filename: str
    content_type: Optional[str] = None
    size: int = 0
    category: Optional[str] = None
    uploaded_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: list[DocumentItem]


def _doc_to_item(doc: LeadDocument) -> DocumentItem:
    return DocumentItem(
        id=doc.id,
        lead_id=doc.lead_id,
        filename=doc.filename,
        content_type=doc.content_type,
        size=doc.size,
        category=doc.category,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at,
    )


def _get_lead(lead_id: str, db: Session, current_user: User) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    enforce_client_scope(lead.client_id, current_user)
    enforce_agent_assignment(lead, current_user)
    return lead


@router.post("/{lead_id}/documents", response_model=DocumentItem, status_code=201)
def upload_document(
    lead_id: str,
    file: UploadFile = File(...),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Upload a file attachment for a lead (agent/admin only)."""
    lead = _get_lead(lead_id, db, current_user)

    cat = (category or "OTHER").upper()
    if cat not in ALLOWED_CATEGORIES:
        cat = "OTHER"

    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="File too large (max 25 MB)."
        )
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    # Sanitise the original filename for display
    orig = (file.filename or "document").strip()
    orig = Path(orig).name  # strip any path components

    stored = f"{uuid.uuid4().hex}_{orig}"
    lead_dir = UPLOAD_BASE / lead_id
    lead_dir.mkdir(parents=True, exist_ok=True)
    (lead_dir / stored).write_bytes(data)

    who = current_user.email if current_user else "system"
    doc = LeadDocument(
        lead_id=lead.id,
        filename=orig,
        stored_name=stored,
        content_type=file.content_type,
        size=len(data),
        category=cat,
        uploaded_by=who,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_to_item(doc)


@router.get("/{lead_id}/documents", response_model=DocumentListResponse)
def list_documents(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents attached to a lead."""
    lead = _get_lead(lead_id, db, current_user)
    docs = (
        db.query(LeadDocument)
        .filter(LeadDocument.lead_id == lead.id)
        .order_by(LeadDocument.created_at.desc())
        .all()
    )
    return DocumentListResponse(documents=[_doc_to_item(d) for d in docs])


@router.get("/{lead_id}/documents/{doc_id}/download")
def download_document(
    lead_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream a document back to the client (auth-gated)."""
    _get_lead(lead_id, db, current_user)  # lead must exist + be in scope
    doc = (
        db.query(LeadDocument)
        .filter(LeadDocument.id == doc_id, LeadDocument.lead_id == lead_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = UPLOAD_BASE / doc.lead_id / doc.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
    )


@router.delete("/{lead_id}/documents/{doc_id}", status_code=204)
def delete_document(
    lead_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner()),
):
    """Delete a document (admin only)."""
    _get_lead(lead_id, db, current_user)
    doc = (
        db.query(LeadDocument)
        .filter(LeadDocument.id == doc_id, LeadDocument.lead_id == lead_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove from disk
    path = UPLOAD_BASE / doc.lead_id / doc.stored_name
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass

    db.delete(doc)
    db.commit()
    return None
