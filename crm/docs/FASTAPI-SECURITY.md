# RankBuilder CRM — FastAPI Security Guide

> **Source:** Adapted from the ECC project (github.com/affaan-m/ECC, MIT license) —
> `skills/fastapi-patterns/SKILL.md`. Tailored for the RankBuilder CRM backend
> (FastAPI + SQLAlchemy + JWT auth).
>
> **Location:** `rankbuilder/crm/backend/`
> **Stack:** FastAPI, SQLAlchemy (SQLite → PostgreSQL when scaled), JWT auth (python-jose),
> bcrypt (passlib), Brevo SMTP.

---

## 🚨 Priority: Fix the hardcoded JWT secret

**FIXED 2026-08-27:** `backend/routes/auth.py` had a hardcoded default secret.
It now reads from the `CRM_JWT_SECRET` env var (with a dev-only fallback):

```python
SECRET_KEY = os.environ.get("CRM_JWT_SECRET", "rankbuilder-crm-dev-only-insecure-secret")
```

**Deployed:** `CRM_JWT_SECRET` set in the VPS systemd service + local backup env.
**Stored in Vaultwarden:** item **"RankBuilder CRM JWT Secret"** (id `c443257c-640d-457c-859b-c41818e4946a`).
Generate a new value with: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

> ⚠️ If you ever rotate the secret, all existing JWTs become invalid (users must re-login).

---

## When to Use

- Reviewing the CRM's authentication / authorization
- Adding new API endpoints
- Configuring production security
- Auditing the CRM for vulnerabilities

---

## 1. Authentication & Authorization

### Current state (good)
- JWT auth via `OAuth2PasswordBearer` + `python-jose`
- Passwords hashed with bcrypt (`passlib.CryptContext(schemes=["bcrypt"])`)
- Role-based access (`SYSTEM_ADMIN`, `CLIENT_ADMIN`, `AGENT`, `VIEWER`)
- `enforce_client_scope` + `enforce_agent_assignment` for object-level access

### To verify / improve
- **JWT secret from env** (see priority fix above)
- **Token expiry** — `ACCESS_TOKEN_EXPIRE_HOURS` should be short (e.g. 8h, not days)
- **Rate-limit login** — add `slowapi` or similar to `/api/auth/login` to prevent brute-force
- **Password policy** — enforce minimum length/complexity on register/reset
- **Token revocation** — consider a token blacklist or short-lived tokens for high-risk actions

---

## 2. CORS

### Current state
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:5174",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174",
        "https://dashboard.fortressblinds.co.za",
        "https://agent.fortressblinds.co.za",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Good:** origins are explicit (not `*`), credentials allowed only for known origins.
**Verify:** `allow_methods=["*"]` and `allow_headers=["*"]` are broad — tighten to only
what the frontend needs if possible.

---

## 3. Input Validation (Pydantic v2)

- Use Pydantic schemas for all request bodies (the CRM does this via `backend/schemas.py`)
- Validate email format (`EmailStr`), phone, and required fields
- Never trust client-supplied IDs — always scope queries to the authenticated user's client
- The CRM already has `EmailStr` validation + phone auto-format (from 2026-08-20 work)

---

## 4. SQL Injection

- Use SQLAlchemy ORM (the CRM does) — it parameterizes queries
- Never build raw SQL with string interpolation
- Audit any raw SQL in reports/scoring for parameterization

---

## 5. Secrets & Config

- **Never hardcode secrets** (see the JWT secret priority fix)
- Use env vars for: `CRM_JWT_SECRET`, `BREVO_API_KEY`, `OPENROUTER_API_KEY`, DB creds
- The systemd service already passes env vars — add `CRM_JWT_SECRET` there
- `.env` is gitignored; never commit it

---

## 6. Public Endpoints (attack surface)

The CRM has public endpoints (`/api/leads/public`, `/api/facebook/webhook`,
`/api/whatsapp/webhook`) that accept unauthenticated input. These are **prime attack
targets** (like the HOS site):

- **`/api/leads/public`** — uses an `X-API-Key` header. Verify the key is:
  - Long and random
  - Stored in env, not hardcoded
  - Rate-limited (prevent spam/abuse)
- **Webhooks** (facebook/whatsapp) — verify tokens, validate signatures, rate-limit
- **Sanitize all public input** — treat it as untrusted (prompt injection, malicious payloads)

---

## 7. Deployment Security

- Run behind nginx (the CRM does — `dashboard.fortressblinds.co.za`)
- HTTPS via Let's Encrypt (in place)
- Restrict DB access (SQLite is local; if moving to PostgreSQL, bind to localhost)
- Keep dependencies patched (`pip-audit` in CI)
- Back up the DB regularly

---

## 8. CRM-Specific Review Checklist

- [ ] **JWT secret from env** (not hardcoded) — PRIORITY
- [ ] Login rate-limited
- [ ] Public endpoints (leads/public, webhooks) rate-limited + key/signature verified
- [ ] No hardcoded secrets anywhere in `backend/`
- [ ] Token expiry is reasonable (not days/weeks)
- [ ] CORS origins explicit (no `*`)
- [ ] All queries use ORM (no raw SQL interpolation)
- [ ] Error responses don't leak internals
- [ ] `DEBUG`/verbose logging off in production
