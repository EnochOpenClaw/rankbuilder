"""
RankBuilder CRM — FastAPI Application
Phase 1: Lead capture, qualification, and HOS client portal
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import engine, Base
from backend.routes import leads, clients, dashboard

app = FastAPI(
    title="RankBuilder CRM",
    version="0.1.0",
    description="Autonomous SEO lead generation CRM",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(clients.router, prefix="/api/clients", tags=["Clients"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])


@app.on_event("startup")
def startup():
    """Create all tables on startup."""
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "service": "rankbuilder-crm"}
