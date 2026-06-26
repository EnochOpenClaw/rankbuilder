"""
RankBuilder CRM — Pydantic Schemas
Phase 1 request/response models
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Enums (mirrored from database) ────────────────────────────────────────────

class LeadSource(str):
    HARO = "HARO"
    CONNECTIVELY = "CONNECTIVELY"
    GUEST_OUTREACH = "GUEST_OUTREACH"
    WEB_SEARCH = "WEB_SEARCH"
    MANUAL = "MANUAL"


class LeadStatus(str):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    QUALIFIED = "QUALIFIED"
    SENT = "SENT"
    CONTACTED = "CONTACTED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class LeadType(str):
    VALID = "VALID"
    INVALID = "INVALID"
    FOLLOW_UP = "FOLLOW_UP"


# ── Lead Schemas ──────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    """API payload for creating a new lead (from RankBuilder agents)."""
    client_id: str
    campaign_id: Optional[str] = None
    source: str  # LeadSource enum value
    source_query: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    message_excerpt: Optional[str] = None
    pitch_sent: Optional[str] = None
    quality_score: Optional[int] = Field(None, ge=1, le=5)
    lead_type: Optional[str] = None  # VALID / INVALID / FOLLOW_UP
    notes: Optional[str] = None

    class Config:
        use_enum_values = True


class LeadUpdate(BaseModel):
    """API payload for updating lead fields."""
    status: Optional[str] = None
    lead_type: Optional[str] = None
    quality_score: Optional[int] = Field(None, ge=1, le=5)
    client_response: Optional[str] = None
    notes: Optional[str] = None
    conversion_status: Optional[str] = None  # CONVERTED or LOST

    class Config:
        use_enum_values = True


class LeadResponse(BaseModel):
    """Full lead record as returned by the API."""
    id: str
    client_id: str
    campaign_id: Optional[str]
    source: str
    source_query: Optional[str]
    status: str
    lead_type: Optional[str]
    quality_score: Optional[int]
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    company_name: Optional[str]
    company_website: Optional[str]
    message_excerpt: Optional[str]
    pitch_sent: Optional[str]
    sent_to_client_at: Optional[datetime]
    client_response: Optional[str]
    conversion_status: Optional[str]
    converted_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    """Paginated lead list."""
    total: int
    leads: list[LeadResponse]


# ── Client Schemas ─────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    company_name: str
    contact_email: str
    notification_channel: str = "EMAIL"
    notification_target: str


class ClientResponse(BaseModel):
    id: str
    company_name: str
    contact_email: str
    notification_channel: str
    notification_target: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Dashboard Schemas ───────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_leads: int
    qualified_leads: int
    sent_to_client: int
    converted: int
    lost: int
    qualification_rate: float  # percentage
    conversion_rate: float      # percentage
    avg_response_time_hours: Optional[float]


class SourceBreakdown(BaseModel):
    source: str
    count: int
    qualified_count: int


class LeadsOverTime(BaseModel):
    date: str
    count: int


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    source_breakdown: list[SourceBreakdown]
    leads_over_time: list[LeadsOverTime]
