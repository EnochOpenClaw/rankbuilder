"""
RankBuilder CRM — Auth Schemas
Phase 1: User registration, login, JWT tokens
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserRole(str):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    CLIENT_ADMIN = "CLIENT_ADMIN"
    VIEWER = "VIEWER"


# ── Request / Response Schemas ─────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    client_id: str | None = None  # None for SYSTEM_ADMIN
    role: str = "VIEWER"  # SYSTEM_ADMIN, CLIENT_ADMIN, VIEWER


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    client_id: str | None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str  # user id
    role: str
    client_id: str | None = None
