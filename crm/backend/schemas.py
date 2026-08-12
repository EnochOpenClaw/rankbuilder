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
    WEBSITE = "WEBSITE"
    FACEBOOK = "FACEBOOK"
    DIRECT_MAIL = "DIRECT_MAIL"
    CALL_IN = "CALL_IN"
    WEB_SEARCH = "WEB_SEARCH"
    MANUAL = "MANUAL"
    WHATSAPP = "WHATSAPP"
    PPC = "PPC"
    WORD_OF_MOUTH = "WORD_OF_MOUTH"


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
    """API payload for creating a new lead (from RankBuilder agents or public capture)."""
    client_id: str
    campaign_id: Optional[str] = None
    source: str  # LeadSource enum value
    source_query: Optional[str] = None
    source_detail: Optional[str] = None  # e.g. "Homepage Quote Form", "Facebook Lead Ad"
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
    # Marketing attribution
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    # Location
    location: Optional[str] = None  # suburb / city / province

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
    source_detail: Optional[str] = None
    location: Optional[str] = None

    class Config:
        use_enum_values = True


class LeadPublicCreate(BaseModel):
    """Public lead capture — no auth required, uses a client API token."""
    contact_name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None
    product_interest: Optional[str] = None  # what they enquired about
    location: Optional[str] = None  # suburb / city
    message: Optional[str] = None  # their enquiry message
    # UTM tracking
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

    class Config:
        use_enum_values = True


class LeadPublicResponse(BaseModel):
    success: bool
    lead_id: Optional[str] = None
    message: str


class LeadResponse(BaseModel):
    """Full lead record as returned by the API."""
    id: str
    client_id: str
    campaign_id: Optional[str]
    source: str
    source_query: Optional[str]
    source_detail: Optional[str]
    utm_source: Optional[str]
    utm_medium: Optional[str]
    utm_campaign: Optional[str]
    location: Optional[str]
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
    # ── Sales rep assignment & follow-up ───────────────────────────────────
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    assigned_at: Optional[datetime] = None
    last_follow_up_at: Optional[datetime] = None
    follow_up_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadAssignRequest(BaseModel):
    """Reassign a lead to a specific rep."""
    assigned_to: str  # rep email
    assigned_to_name: Optional[str] = None


class LeadFollowUpRequest(BaseModel):
    """Log a follow-up action on a lead."""
    note: str  # what was done during the follow-up
    changed_by: Optional[str] = None
    activity_type: str = "CALL"  # CALL | EMAIL | WHATSAPP | SMS | NOTE | OTHER
    outcome: Optional[str] = None  # NO_ANSWER | LEFT_VOICEMAIL | SPOKE | SENT | RECEIVED | OTHER
    occurred_at: Optional[datetime] = None  # when the attempt happened (defaults to now)


class LeadFollowUpResponse(BaseModel):
    lead_id: str
    follow_up_count: int
    last_follow_up_at: Optional[datetime]
    message: str


class LeadActivityItem(BaseModel):
    """A single stacked activity/attempt on a lead timeline."""
    id: str
    lead_id: str
    activity_type: str
    outcome: Optional[str]
    note: Optional[str]
    occurred_at: Optional[datetime]
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


class LeadActivityResponse(BaseModel):
    activities: list[LeadActivityItem]


class EmailLogCreate(BaseModel):
    """Attach an email to a lead's timeline (short-term manual entry)."""
    direction: str = "OUTBOUND"  # INBOUND | OUTBOUND
    subject: Optional[str] = None
    body: Optional[str] = None
    from_email: Optional[str] = None
    to_email: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_by: Optional[str] = None


class EmailLogItem(BaseModel):
    id: str
    lead_id: str
    direction: str
    subject: Optional[str]
    body: Optional[str]
    from_email: Optional[str]
    to_email: Optional[str]
    sent_at: Optional[datetime]
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


class EmailLogResponse(BaseModel):
    emails: list[EmailLogItem]


class NotificationGroupCreate(BaseModel):
    """Create a named notification group for a client."""
    client_id: str
    name: str
    description: Optional[str] = None
    members: list[dict] = []  # [{target, name, notification_type}]


class NotificationGroupItem(BaseModel):
    id: str
    client_id: str
    name: str
    description: Optional[str]
    members: list[dict] = []

    class Config:
        from_attributes = True


class NotificationGroupResponse(BaseModel):
    groups: list[NotificationGroupItem]


class LeadHistoryItem(BaseModel):
    id: str
    lead_id: str
    field_changed: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: str
    changed_at: datetime

    class Config:
        from_attributes = True


class LeadHistoryResponse(BaseModel):
    history: list[LeadHistoryItem]


class LeadListResponse(BaseModel):
    """Paginated lead list."""
    total: int
    leads: list[LeadResponse]


# ── Client Schemas ─────────────────────────────────────────────────────────────

# ── Campaign Schemas ────────────────────────────────────────────────────────────

class CampaignStatus(str):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class CampaignCreate(BaseModel):
    client_id: str
    name: str
    channel: str  # LeadSource enum value
    status: str = "ACTIVE"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class CampaignResponse(BaseModel):
    id: str
    client_id: str
    name: str
    channel: str
    status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    lead_count: int = 0
    qualified_count: int = 0
    converted_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    total: int
    campaigns: list[CampaignResponse]


class ClientCreate(BaseModel):
    company_name: str
    contact_email: str
    notification_channel: str = "EMAIL"
    notification_target: str


class ClientOnboardRequest(BaseModel):
    """Provision a new client with admin user + API key + default campaign."""
    company_name: str
    contact_email: str
    admin_email: str
    admin_password: str
    admin_full_name: str = ""
    notification_channel: str = "EMAIL"
    notification_target: str = ""
    campaign_name: str = ""


class ClientResponse(BaseModel):
    id: str
    company_name: str
    contact_email: str
    notification_channel: str
    notification_target: str
    api_key: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class ClientOnboardResponse(BaseModel):
    client: ClientResponse
    api_key: str
    admin_user: dict
    admin_password: str = ""
    campaign: dict


# ── Dashboard Schemas ───────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_leads: int
    qualified_leads: int
    sent_to_client: int
    converted: int
    lost: int
    qualification_rate: float  # percentage
    conversion_rate: float      # percentage
    avg_response_time_hours: Optional[float]  # overall mean (hours)
    p50_response_time_hours: Optional[float]  # median
    p95_response_time_hours: Optional[float]  # 95th percentile


class SourceBreakdown(BaseModel):
    source: str
    count: int
    qualified_count: int
    avg_response_time_hours: Optional[float] = None
    leads_sent: int = 0


class LeadsOverTime(BaseModel):
    date: str
    count: int


class FunnelStage(BaseModel):
    stage: str
    count: int


class RepBreakdown(BaseModel):
    """Per-sales-rep productivity stats."""
    rep_email: str
    rep_name: str
    assigned_leads: int = 0
    follow_ups: int = 0          # total follow-up actions logged
    contacted: int = 0           # leads moved to CONTACTED
    converted: int = 0           # leads converted
    lost: int = 0                # leads lost
    avg_response_hours: Optional[float] = None
    last_follow_up_at: Optional[datetime] = None


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    source_breakdown: list[SourceBreakdown]
    leads_over_time: list[LeadsOverTime]
    funnel: list[FunnelStage]
    rep_breakdown: list[RepBreakdown] = []
