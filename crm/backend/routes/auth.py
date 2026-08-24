"""
RankBuilder CRM — Auth Routes
POST /api/auth/register  — First user bootstrap (no auth required)
POST /api/auth/login      — Email + password → JWT
GET  /api/auth/me         — Current user info
POST /api/auth/users      — Create user (SYSTEM_ADMIN only)
GET  /api/auth/users      — List users (SYSTEM_ADMIN / CLIENT_ADMIN)
DELETE /api/auth/users/{id} — Disable user (SYSTEM_ADMIN only)
POST  /api/auth/users/{id}/reset-password — Reset a user's password (SYSTEM_ADMIN only)
"""

import uuid
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt
from pydantic import BaseModel

from backend.database import get_db, User, UserRole, Client
from backend.auth import UserCreate, UserResponse, TokenResponse

# ── Config ──────────────────────────────────────────────────────────────────────
SECRET_KEY = "rankbuilder-crm-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Corrupt/unknown hash format (e.g. missing bcrypt prefix) must not crash login.
        # Treat as invalid credentials -> clean 401 instead of a 500.
        return False


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db),
) -> User:
    """Decode JWT and return the current user."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_role(*roles: str):
    """Dependency — require user to have one of the specified roles."""
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role.value not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"This action requires one of: {', '.join(roles)}",
            )
        return current_user
    return checker


def require_client_access(
    current_user: User = Depends(get_current_user),
):
    """
    Dependency — resolve the client a user may operate on.
    - SYSTEM_ADMIN: may pass an explicit client_id (or None for all)
    - CLIENT_ADMIN / VIEWER: forced to their own client_id (scope locked)
    Returns the resolved client_id (or None for SYSTEM_ADMIN/all).
    """
    if current_user.role == UserRole.SYSTEM_ADMIN:
        # SYSTEM_ADMIN can pass any client_id via the request; the caller
        # reads the actual value. This helper is used where a single client
        # scope is required; for cross-client access, routes handle it.
        return current_user
    # Non-admin users are locked to their own client
    if not current_user.client_id:
        raise HTTPException(
            status_code=403,
            detail="Your account is not linked to a client.",
        )
    return current_user


def require_admin_or_owner():
    """Dependency — write-capable roles: SYSTEM_ADMIN, CLIENT_ADMIN, or AGENT.
    AGENT writes are additionally restricted to their OWN assigned leads
    (checked per-endpoint via enforce_agent_assignment)."""
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in (UserRole.SYSTEM_ADMIN, UserRole.CLIENT_ADMIN, UserRole.AGENT):
            raise HTTPException(
                status_code=403,
                detail="This action requires SYSTEM_ADMIN, CLIENT_ADMIN or AGENT.",
            )
        return current_user
    return checker


def enforce_client_scope(requested_client_id, current_user: User):
    """
    Enforce that a user may only access data for their own client.
    Returns the effective client_id to query with.
    - SYSTEM_ADMIN: allowed to use requested_client_id (or None for all)
    - CLIENT_ADMIN/VIEWER: forced to their own client_id
    Raises 403 if a non-admin tries to access another client's data.
    """
    if current_user.role == UserRole.SYSTEM_ADMIN:
        return requested_client_id  # may be None → all clients

    if not current_user.client_id:
        raise HTTPException(status_code=403, detail="Your account is not linked to a client.")

    if requested_client_id and requested_client_id != current_user.client_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access data for your own client.",
        )
    return current_user.client_id


def enforce_agent_assignment(lead, current_user: User):
    """AGENTs may only read/write leads assigned to them. No-op for admins."""
    if current_user.role == UserRole.AGENT:
        if lead.assigned_to != current_user.email:
            raise HTTPException(
                status_code=403,
                detail="AGENTs can only access leads assigned to them.",
            )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: UserCreate, db=Depends(get_db)):
    """
    Bootstrap endpoint — first user ever becomes SYSTEM_ADMIN.
    All subsequent user creation goes through POST /auth/users (SYSTEM_ADMIN only).
    """
    user_count = db.query(User).filter(User.is_active == 1).count()

    if user_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Registration closed. Ask a SYSTEM_ADMIN to create your account.",
        )

    user = User(
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        client_id=None,
        role=UserRole.SYSTEM_ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        client_id=user.client_id,
        role=user.role.value,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """Email + password login → JWT token."""
    user = db.query(User).filter(User.email == form_data.username.lower()).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token({
        "sub": user.id,
        "role": user.role.value,
        "client_id": user.client_id,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            client_id=user.client_id,
            role=user.role.value,
            created_at=user.created_at,
            must_change_password=user.must_change_password or 0,
        ),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        client_id=current_user.client_id,
        role=current_user.role.value,
        created_at=current_user.created_at,
        must_change_password=current_user.must_change_password or 0,
    )


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    new_password: str  # SYSTEM_ADMIN sets a new password for another user


@router.post("/change-password", response_model=UserResponse)
def change_password(
    payload: ChangePasswordRequest,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the current user's password. Clears must_change_password flag."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.must_change_password = 0
    db.commit()
    db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        client_id=current_user.client_id,
        role=current_user.role.value,
        created_at=current_user.created_at,
        must_change_password=0,
    )


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreate,
    db=Depends(get_db),
    _: User = Depends(require_role("SYSTEM_ADMIN")),
):
    """Create a new user. SYSTEM_ADMIN only."""
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    if payload.client_id:
        client = db.query(Client).filter(Client.id == payload.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

    role = UserRole(payload.role) if payload.role else UserRole.VIEWER

    user = User(
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        client_id=payload.client_id,
        role=role,
        must_change_password=1,  # new users must change password on first login
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Optionally email the user their login details
    if payload.send_welcome:
        _send_login_details(user, payload.password, role=role.value)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        client_id=user.client_id,
        role=user.role.value,
        created_at=user.created_at,
        must_change_password=1,
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db=Depends(get_db),
    current_user: User = Depends(require_role("SYSTEM_ADMIN", "CLIENT_ADMIN")),
    client_id: str | None = None,
):
    """
    List users.
    - SYSTEM_ADMIN: all active users, optionally filtered by client_id
    - CLIENT_ADMIN: only users belonging to their own client
    """
    q = db.query(User).filter(User.is_active == 1)

    if current_user.role == UserRole.CLIENT_ADMIN:
        q = q.filter(User.client_id == current_user.client_id)
    elif client_id:
        q = q.filter(User.client_id == client_id)

    users = q.order_by(User.created_at.desc()).all()
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            client_id=u.client_id,
            role=u.role.value,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_role("SYSTEM_ADMIN")),
):
    """Soft-delete a user (sets is_active=0). SYSTEM_ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user.is_active = 0
    user.updated_at = datetime.utcnow()
    db.commit()


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: str,
    payload: PasswordResetRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_role("SYSTEM_ADMIN")),
):
    """SYSTEM_ADMIN resets another user's password. Sets must_change_password flag
    so the user is prompted to set their own password on next login."""
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = 1
    user.is_active = 1  # resetting re-enables the account if it was disabled
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        client_id=user.client_id,
        role=user.role.value,
        created_at=user.created_at,
        must_change_password=1,
    )


# ── Welcome email (login details) ──────────────────────────────────────────────

def _send_login_details(user, temp_password: str, role: str = "VIEWER") -> None:
    """
    Email a newly-created user their login details: site address, email, and a
    temporary password they must change on first login.
    """
    brevo_key = os.environ.get("BREVO_API_KEY", "")
    if not brevo_key:
        import logging
        logging.getLogger("crm.auth").warning("BREVO_API_KEY not set - welcome email not sent")
        return

    site_url = os.environ.get("CRM_PORTAL_URL", "https://dashboard.fortressblinds.co.za")
    sender_email = os.environ.get("SENDER_EMAIL", "ai@fortressblinds.co.za")
    sender_name = os.environ.get("SENDER_NAME", "RankBuilder CRM")

    subject = "🎉 Your RankBuilder CRM Login Details"
    html = f"""
<!DOCTYPE html>
<html><body style='font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>🎉 Welcome, {user.full_name}!</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>Your RankBuilder CRM account has been created.</p>
    </div>
    <p style='color:#555;font-size:14px;'>Here are your login details:</p>
    <div style='background:#f5f5f5;border-radius:8px;padding:16px;margin:16px 0;font-size:14px;'>
      <p style='margin:0 0 8px;'><strong>Site address:</strong><br/><a href="{site_url}" style="color:#1e88e5;">{site_url}</a></p>
      <p style='margin:0 0 8px;'><strong>Email:</strong><br/>{user.email}</p>
      <p style='margin:0 0 8px;'><strong>Temporary password:</strong><br/><code style='background:#eef;padding:2px 8px;border-radius:4px;'>{temp_password}</code></p>
      <p style='margin:0;'><strong>Role:</strong> {role}</p>
    </div>
    <div style='margin-top:16px;padding:14px;background:#fff8e1;border-radius:8px;'>
      <p style='margin:0;color:#666;font-size:13px;'><strong>Important:</strong> For security, you will be asked to change your password the first time you log in.</p>
    </div>
    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>RankBuilder CRM · Powered by AgenticFlows</p>
  </div>
</body></html>"""

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": user.email, "name": user.full_name}],
        "subject": subject,
        "htmlContent": html,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email", data=data,
        headers={"Content-Type": "application/json", "api-key": brevo_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            import logging
            logging.getLogger("crm.auth").info(f"Welcome email sent to {user.email}")
    except Exception as e:
        import logging
        logging.getLogger("crm.auth").exception(f"Welcome email failed for {user.email}: {e}")
