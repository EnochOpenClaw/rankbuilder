"""
RankBuilder CRM — SQLite Database + SQLAlchemy Models
Phase 1 data model: leads, clients, campaigns
"""

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Enum as SAEnum,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.pool import QueuePool

import enum

# ── Enums ──────────────────────────────────────────────────────────────────────

class LeadSource(str, enum.Enum):
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


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    QUALIFIED = "QUALIFIED"
    SENT = "SENT"
    CONTACTED = "CONTACTED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class LeadType(str, enum.Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    FOLLOW_UP = "FOLLOW_UP"


class CampaignStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class UserRole(str, enum.Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    CLIENT_ADMIN = "CLIENT_ADMIN"
    AGENT = "AGENT"
    VIEWER = "VIEWER"


class NotificationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    WEBHOOK = "WEBHOOK"


# ── Base ──────────────────────────────────────────────────────────────────────

Base = declarative_base()


# ── Models ────────────────────────────────────────────────────────────────────

class Client(Base):
    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key = Column(String(64), unique=True, nullable=True, index=True)  # public token for lead capture
    company_name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False)
    notification_channel = Column(
        SAEnum(NotificationChannel), default=NotificationChannel.EMAIL
    )
    notification_target = Column(String(255), nullable=False)  # email or webhook URL
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    leads = relationship("Lead", back_populates="client", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="client", cascade="all, delete-orphan")


class LeadSourceModel(Base):
    """Admin-managed lead source values (trackable for reporting)."""

    __tablename__ = "lead_sources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False, index=True)  # e.g. "HARO", "MANUAL"
    name = Column(String(100), nullable=False)  # display label e.g. "HARO"
    is_active = Column(Integer, default=1)  # 1 = shown in dropdown/reports
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoringRule(Base):
    """Configurable lead-scoring rule (SYSTEM_ADMIN managed).

    field: which lead attribute to evaluate (source, has_phone, has_website,
           lead_type, location, message_keyword, no_email, age_days)
    operator: eq / ne / contains / gt / lt / is_true / is_false
    value: the comparison value (string or number)
    points: points to add (positive) or subtract (negative)
    """

    __tablename__ = "scoring_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True)  # NULL = global rule
    field = Column(String(50), nullable=False)  # source, has_phone, has_website, lead_type, location, message_keyword, no_email, age_days
    operator = Column(String(20), nullable=False, default="eq")  # eq, ne, contains, gt, lt, is_true, is_false
    value = Column(String(255), nullable=True)
    points = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=False)
    channel = Column(SAEnum(LeadSource), nullable=False)
    status = Column(SAEnum(CampaignStatus), default=CampaignStatus.ACTIVE)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=True)

    # Source tracking
    source = Column(SAEnum(LeadSource), nullable=False)
    source_query = Column(String(500), nullable=True)  # e.g. "aluminum shutters sa"
    source_detail = Column(String(255), nullable=True)  # e.g. "Homepage Quote Form", "Facebook Lead Ad"

    # Marketing attribution
    utm_source = Column(String(100), nullable=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)

    # Location
    location = Column(String(255), nullable=True)  # suburb / city / province
    address = Column(String(500), nullable=True)   # full street address (agent-confirmed)

    # Classification
    status = Column(SAEnum(LeadStatus), default=LeadStatus.NEW)
    lead_type = Column(SAEnum(LeadType), nullable=True)
    quality_score = Column(Integer, nullable=True)  # 1-5

    # Contact info
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    company_website = Column(String(500), nullable=True)

    # Lead context
    message_excerpt = Column(Text, nullable=True)   # what lead said / query context
    pitch_sent = Column(Text, nullable=True)          # what RankBuilder sent

    # Client delivery
    sent_to_client_at = Column(DateTime, nullable=True)
    client_response = Column(Text, nullable=True)

    # Outcome
    conversion_status = Column(String(50), nullable=True)  # CONVERTED or LOST
    converted_at = Column(DateTime, nullable=True)
    # ── Sales value ──────────────────────────────────────────────────────
    quote_amount = Column(Float, nullable=True)      # value of the quote sent (R)
    estimated_deal_value = Column(Float, nullable=True)  # est. value before quote (R)
    created_by = Column(String(255), nullable=True)  # email of user who created the lead
    payment_status = Column(String(20), nullable=True)  # PENDING / RECEIVED

    # Internal
    notes = Column(Text, nullable=True)

    # ── Sales rep assignment & follow-up ───────────────────────────────────
    assigned_to = Column(String(255), nullable=True)          # rep email
    assigned_to_name = Column(String(255), nullable=True)     # rep display name
    assigned_at = Column(DateTime, nullable=True)
    last_follow_up_at = Column(DateTime, nullable=True)
    follow_up_count = Column(Integer, default=0)
    reminder_stage = Column(Integer, default=0)  # follow-up escalation: 0=none,1=24h,2=48h,3=72h-manager
    last_sla_alert_at = Column(DateTime, nullable=True)  # last SLA breach alert time (dedup)

    archived = Column(Integer, default=0)  # 1 = archived (soft delete)
    archived_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="leads")
    campaign = relationship("Campaign", back_populates="leads")
    history = relationship("LeadHistory", back_populates="lead", cascade="all, delete-orphan")
    activities = relationship("LeadActivity", back_populates="lead", cascade="all, delete-orphan")
    emails = relationship("EmailLog", back_populates="lead", cascade="all, delete-orphan")
    documents = relationship("LeadDocument", back_populates="lead", cascade="all, delete-orphan")


class LeadHistory(Base):
    """Audit trail for lead status transitions."""

    __tablename__ = "lead_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=False)
    field_changed = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)
    changed_by = Column(String(255), nullable=True)  # "system" or user email

    lead = relationship("Lead", back_populates="history")


class NotificationGroup(Base):
    """Named group of notification recipients for a client (e.g. 'Sales Team')."""

    __tablename__ = "notification_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    name = Column(String(100), nullable=False)                 # e.g. "Sales Team"
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")
    members = relationship("NotificationSetting", back_populates="group", cascade="all, delete-orphan")


class NotificationSetting(Base):
    """Per-client notification delivery settings (email/SMS/webhook)."""

    __tablename__ = "notification_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    group_id = Column(String(36), ForeignKey("notification_groups.id"), nullable=True)
    notification_type = Column(String(20), nullable=False)  # EMAIL | SMS | WEBHOOK
    target = Column(String(255), nullable=True)              # email address, phone, or webhook URL
    name = Column(String(100), nullable=True)                 # friendly recipient name
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")
    group = relationship("NotificationGroup", back_populates="members")


class LeadActivity(Base):
    """Stacked activity log for a lead — every call/email/contact attempt gets its own row.

    This replaces the old single 'last_follow_up_at' counter model. Each attempt
    (e.g. called 08:00 no answer, called 10:00 no answer) is preserved as a
    separate entry so the full history is visible on the lead timeline.
    """

    __tablename__ = "lead_activities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=False)
    activity_type = Column(String(20), nullable=False)  # CALL | EMAIL | WHATSAPP | SMS | NOTE | OTHER
    outcome = Column(String(20), nullable=True)          # NO_ANSWER | LEFT_VOICEMAIL | SPOKE | SENT | RECEIVED | OTHER
    note = Column(Text, nullable=True)                   # what happened during this attempt
    occurred_at = Column(DateTime, default=datetime.utcnow)  # when the attempt happened
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)      # user email

    lead = relationship("Lead", back_populates="activities")


class EmailLog(Base):
    """Short-term email log — attach sent/received emails to a lead's timeline.

    Phase 1: manual entry (paste email subject/body). Phase 2: Office 365 / Outlook
    Graph integration to auto-capture.
    """

    __tablename__ = "email_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=False)
    direction = Column(String(10), nullable=False)  # INBOUND | OUTBOUND
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    from_email = Column(String(255), nullable=True)
    to_email = Column(String(255), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    lead = relationship("Lead", back_populates="emails")


class LeadDocument(Base):
    """Attached documents for a lead — response emails, quotes sent, etc.

    Files are stored on disk under {UPLOAD_DIR}/{lead_id}/; this row holds the
    metadata (original filename, stored name, size, category).
    """

    __tablename__ = "lead_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=False)
    filename = Column(String(500), nullable=False)   # original display name
    stored_name = Column(String(500), nullable=False) # uuid-based name on disk
    content_type = Column(String(255), nullable=True)
    size = Column(Integer, default=0)
    category = Column(String(50), nullable=True)     # EMAIL | QUOTE | RESPONSE | OTHER
    uploaded_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="documents")


class User(Base):
    """CRM user — email + password auth, role-based access."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True)  # NULL for SYSTEM_ADMIN
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.VIEWER)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Integer, default=1)  # SQLite bool (0/1)
    must_change_password = Column(Integer, default=1)  # 1 = force password change on next login

    client = relationship("Client", back_populates="users")


Client.users = relationship(
    "User", back_populates="client", cascade="all, delete-orphan"
)


# ── Database setup ─────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / "data" / "rankbuilder_crm.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency — get a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_lead_sources(db):
    """Populate lead_sources table from the enum defaults if empty."""
    existing = db.query(LeadSourceModel).count()
    if existing > 0:
        return
    defaults = [
        "HARO", "CONNECTIVELY", "GUEST_OUTREACH", "WEBSITE", "FACEBOOK",
        "DIRECT_MAIL", "CALL_IN", "WEB_SEARCH", "MANUAL", "WHATSAPP",
        "PPC", "WORD_OF_MOUTH",
    ]
    for i, code in enumerate(defaults):
        db.add(LeadSourceModel(code=code, name=code, sort_order=i))
    db.commit()
