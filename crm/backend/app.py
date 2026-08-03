"""
RankBuilder CRM — FastAPI Application
Phase 1: Lead capture, qualification, and HOS client portal
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import engine, Base
from backend.routes import leads, clients, dashboard, auth, notifications, public

# Build artifact path — served as static files in production
BACKEND_DIR   = Path(__file__).parent   # .../crm/backend/
FRONTEND_DIST = BACKEND_DIR.parent / 'frontend' / 'dist'

app = FastAPI(
    title="RankBuilder CRM",
    version="0.1.0",
    description="Autonomous SEO lead generation CRM",
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


@app.on_event("startup")
def startup():
    """Create all tables on startup."""
    Base.metadata.create_all(bind=engine)


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
