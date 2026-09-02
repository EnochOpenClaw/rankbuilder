"""
RankBuilder CRM — FastAPI Application
Phase 1: Lead capture, qualification, and HOS client portal
"""

import os
from pathlib import Path

import json
import re
import logging
from datetime import datetime, timezone

# ── Logging config ─────────────────────────────────────────────────────────────
# Make crm.* loggers (notifications, leads, etc.) visible at INFO level so email
# sends/failures and notification dispatch are traceable in the service logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("crm.notifications").setLevel(logging.INFO)
logging.getLogger("crm.leads").setLevel(logging.INFO)

from fastapi import FastAPI, APIRouter
from fastapi.routing import APIRoute
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.database import seed_lead_sources, SessionLocal, engine, Base
from backend.scoring import seed_default_rules
from backend.routes import leads, clients, dashboard, auth, notifications, public, facebook, campaigns, whatsapp, documents, sources, scoring, reports, ai, reminders

# Build artifact path — served as static files in production
BACKEND_DIR   = Path(__file__).parent   # .../crm/backend/
FRONTEND_DIST = BACKEND_DIR.parent / 'frontend' / 'dist'

def _fix_utc(obj):
    """Recursively append Z to naive UTC datetime strings (ISO-8601 without
    offset) so the browser renders them in the user's local timezone (SAST).
    Stored times are UTC; without Z, dayjs treats them as local and shows a 2h
    offset. Strings already carrying a timezone (Z or +/-hh:mm) are left alone."""
    dt_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")
    if isinstance(obj, dict):
        return {k: _fix_utc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_utc(v) for v in obj]
    if isinstance(obj, str) and dt_re.match(obj):
        return obj + "Z"
    return obj


class TZAwareJSONResponse(JSONResponse):
    def render(self, content):
        # content is the JSON-serializable model (datetimes already ISO strings
        # from FastAPI's encoder); append Z to naive UTC datetimes before dumps.
        return json.dumps(
            _fix_utc(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="RankBuilder CRM",
    version="0.1.0",
    description="Autonomous SEO lead generation CRM",
    default_response_class=TZAwareJSONResponse,
)

# CORS — allow frontend dev server + production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://dashboard.fortressblinds.co.za",
        "https://agent.fortressblinds.co.za",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(public.router, prefix="/api", tags=["Public"])  # /api/leads/public
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(clients.router, prefix="/api/clients", tags=["Clients"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(facebook.router, prefix="/api", tags=["Facebook"])  # /api/facebook/webhook
app.include_router(whatsapp.router, prefix="/api", tags=["WhatsApp"])  # /api/whatsapp/webhook
app.include_router(documents.router, prefix="/api/leads", tags=["Documents"])  # /api/leads/{id}/documents
app.include_router(reminders.router, prefix="/api/leads", tags=["Reminders"])  # /api/leads/{id}/reminders
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(sources.router, prefix="/api/sources", tags=["Sources"])
app.include_router(scoring.router, prefix="/api/scoring", tags=["Scoring"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])


@app.on_event("startup")
def startup():
    """Create all tables + lightweight migrations on startup."""
    Base.metadata.create_all(bind=engine)
    # ── Migrations (additive ALTER TABLE, idempotent) ──────────────────────
    try:
        from sqlalchemy import text, inspect
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("leads")}
        with engine.begin() as conn:
            if "archived" not in cols:
                conn.execute(text("ALTER TABLE leads ADD COLUMN archived INTEGER DEFAULT 0"))
            if "archived_at" not in cols:
                conn.execute(text("ALTER TABLE leads ADD COLUMN archived_at DATETIME"))
        print("[migrate] leads.archived / leads.archived_at ensured")
        # Campaign.location column (roadside marketing area) — fresh connection
        ccols = {c["name"] for c in insp.get_columns("campaigns")}
        if "location" not in ccols:
            with engine.begin() as conn2:
                conn2.execute(text("ALTER TABLE campaigns ADD COLUMN location VARCHAR(255)"))
        print("[migrate] campaigns.location ensured")
        # EmailLog notification-tracking columns (per-lead notification audit trail)
        ecols = {c["name"] for c in insp.get_columns("email_logs")}
        with engine.begin() as conn3:
            if "notification_type" not in ecols:
                conn3.execute(text("ALTER TABLE email_logs ADD COLUMN notification_type VARCHAR(30)"))
            if "status" not in ecols:
                conn3.execute(text("ALTER TABLE email_logs ADD COLUMN status VARCHAR(20)"))
            if "message_id" not in ecols:
                conn3.execute(text("ALTER TABLE email_logs ADD COLUMN message_id VARCHAR(255)"))
        print("[migrate] email_logs notification columns ensured")
        # Lead partner hand-off columns (cross-client lead hand-off)
        lcols = {c["name"] for c in insp.get_columns("leads")}
        with engine.begin() as conn4:
            if "partner_handoff_id" not in lcols:
                conn4.execute(text("ALTER TABLE leads ADD COLUMN partner_handoff_id VARCHAR(36)"))
            if "partner_handoff_from" not in lcols:
                conn4.execute(text("ALTER TABLE leads ADD COLUMN partner_handoff_from VARCHAR(36)"))
            if "partner_handoff_at" not in lcols:
                conn4.execute(text("ALTER TABLE leads ADD COLUMN partner_handoff_at DATETIME"))
            if "partner_handoff_by" not in lcols:
                conn4.execute(text("ALTER TABLE leads ADD COLUMN partner_handoff_by VARCHAR(255)"))
        print("[migrate] leads partner_handoff columns ensured")
        # Lead read-tracking columns (new-lead highlighting)
        rcols = {c["name"] for c in insp.get_columns("leads")}
        with engine.begin() as conn5:
            if "read_at" not in rcols:
                conn5.execute(text("ALTER TABLE leads ADD COLUMN read_at DATETIME"))
            if "read_by" not in rcols:
                conn5.execute(text("ALTER TABLE leads ADD COLUMN read_by VARCHAR(255)"))
        print("[migrate] leads read_at / read_by ensured")
        # users.must_change_password — password-change-on-first-login flag
        # (model expects it; older DBs lack the column entirely, which breaks login)
        ucols = {c["name"] for c in insp.get_columns("users")}
        with engine.begin() as conn6:
            if "must_change_password" not in ucols:
                conn6.execute(text("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 1"))
        print("[migrate] users.must_change_password ensured")
        # leads.payment_received_at — timestamp when payment_status became RECEIVED
        # (starts the install/quiet window before the post-install follow-up)
        pcols = {c["name"] for c in insp.get_columns("leads")}
        with engine.begin() as conn7:
            if "payment_received_at" not in pcols:
                conn7.execute(text("ALTER TABLE leads ADD COLUMN payment_received_at DATETIME"))
            if "post_install_followup_sent_at" not in pcols:
                conn7.execute(text("ALTER TABLE leads ADD COLUMN post_install_followup_sent_at DATETIME"))
        print("[migrate] leads.payment_received_at / post_install_followup_sent_at ensured")
        # leads — older backups missing columns added in later code (address,
        # sales-value, SLA-escalation fields). Additive + idempotent.
        lcols2 = {c["name"] for c in insp.get_columns("leads")}
        leads_add = {
            "address": "VARCHAR(500)",
            "created_by": "VARCHAR(255)",
            "estimated_deal_value": "FLOAT",
            "last_sla_alert_at": "DATETIME",
            "payment_status": "VARCHAR(20)",
            "quote_amount": "FLOAT",
            "reminder_stage": "INTEGER DEFAULT 0",
        }
        with engine.begin() as conn7:
            for col, ddl in leads_add.items():
                if col not in lcols2:
                    conn7.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {ddl}"))
        print("[migrate] leads missing columns ensured")
    except Exception as e:
        print(f"[migrate] warning: {e}")
    seed_lead_sources(SessionLocal())
    seed_default_rules(SessionLocal())


@app.get("/health")
def health():
    return {"status": "ok", "service": "rankbuilder-crm"}


# ── Serve built frontend (production) ──────────────────────────────────────────
# Serve index.html for non-API GET requests (SPA fallback)
if FRONTEND_DIST.exists():
    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/assets/{path:path}")
    def serve_assets(path: str):
        asset_path = FRONTEND_DIST / "assets" / path
        if asset_path.exists():
            return FileResponse(str(asset_path))
        return {"detail": "Not found"}, 404

    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
