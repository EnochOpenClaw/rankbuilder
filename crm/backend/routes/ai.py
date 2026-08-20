"""
RankBuilder CRM — AI Route
POST /api/ai/draft-reply — Generate an AI auto-response draft for a lead
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from backend.database import User
from backend.routes.auth import get_current_user
from backend.ai_draft import draft_for_lead_id

router = APIRouter()


class DraftRequest(BaseModel):
    lead_id: str


class DraftResponse(BaseModel):
    draft: Optional[str]
    error: Optional[str]


@router.post("/draft-reply", response_model=DraftResponse)
def draft_reply(
    payload: DraftRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate an AI draft reply for a lead."""
    return draft_for_lead_id(payload.lead_id)
