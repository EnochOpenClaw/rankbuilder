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
    DateTime,
    Boolean,
    ForeignKey,
    Enum as SAEnum,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

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

    # Internal
    notes = Column(Text, nullable=True)

    # ── Sales rep assignment & follow-up ───────────────────────────────────
    assigned_to = Column(String(255), nullable=True)          # rep email
    assigned_to_name = Column(String(255), nullable=True)     # rep display name
    assigned_at = Column(DateTime, nullable=True)
    last_follow_up_at = Column(DateTime, nullable=True)
    follow_up_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="leads")
    campaign = relationship("Campaign", back_populates="leads")
    history = relationship("LeadHistory", back_populates="lead", cascade="all, delete-orphan")


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


class NotificationSetting(Base):
    """Per-client notification delivery settings (email/SMS/webhook)."""

    __tablename__ = "notification_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    notification_type = Column(String(20), nullable=False)  # EMAIL | SMS | WEBHOOK
    target = Column(String(255), nullable=True)              # email address, phone, or webhook URL
    name = Column(String(100), nullable=True)                 # friendly recipient name
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")


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
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency — get a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
