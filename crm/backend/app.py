"""
RankBuilder CRM — FastAPI Application
Phase 1: Lead capture, qualification, and HOS client portal
"""

import os
from pathlib import Path

import json
import re
from datetime import datetime, timezone

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
