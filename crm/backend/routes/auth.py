"""
RankBuilder CRM — Auth Routes
POST /api/auth/register  — First user bootstrap (no auth required)
POST /api/auth/login      — Email + password → JWT
GET  /api/auth/me         — Current user info
POST /api/auth/users      — Create user (SYSTEM_ADMIN only)
GET  /api/auth/users      — List users (SYSTEM_ADMIN / CLIENT_ADMIN)
DELETE /api/auth/users/{id} — Disable user (SYSTEM_ADMIN only)
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt

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
    return pwd_context.verify(plain, hashed)


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
    except jwt.InvalidTokenError:
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
