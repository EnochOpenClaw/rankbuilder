"""
RankBuilder CRM — Reports API
GET /api/reports/agent-sales — per-agent: leads, quoted, won/lost, quoted value, predicted value
GET /api/reports/pipeline     — overall pipeline value (quoted + predicted) + funnel drop-off
GET /api/reports/funnel       — stage-by-stage counts + drop-off %
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db, Lead, User, UserRole
from backend.routes.auth import get_current_user, enforce_client_scope

router = APIRouter()

# Conversion probability for predicted sales (quotes sent = high intent, they've met the client)
CONVERSION_PROBABILITY = 0.5  # 50% — quoted leads are more likely to close


@router.get("/agent")
def agent_sales_report(
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-agent sales report — leads, quoted, won, lost, quoted value, predicted value."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)

    leads = q.all()
    agents = {}

    for lead in leads:
        agent_email = lead.assigned_to or "unassigned"
        agent_name = lead.assigned_to_name or (agent_email if agent_email != "unassigned" else "Unassigned")
        if agent_email not in agents:
            agents[agent_email] = {
                "email": agent_email,
                "name": agent_name,
                "leads": 0,
                "quoted": 0,
                "converted": 0,
                "lost": 0,
                "open": 0,
                "quoted_value": 0.0,
                "predicted_value": 0.0,
                "won_value": 0.0,
            }
        a = agents[agent_email]
        a["leads"] += 1
        qa = lead.quote_amount or 0

        if lead.conversion_status == "CONVERTED":
            a["converted"] += 1
            a["won_value"] += qa
            a["quoted"] += 1 if qa > 0 else 0
            a["quoted_value"] += qa
        elif lead.conversion_status == "LOST":
            a["lost"] += 1
            if qa > 0:
                a["quoted"] += 1
                a["quoted_value"] += qa
        else:
            a["open"] += 1
            if qa > 0:
                a["quoted"] += 1
                a["quoted_value"] += qa
                a["predicted_value"] += round(qa * CONVERSION_PROBABILITY, 2)

    # Sort by quoted_value desc
    result = sorted(agents.values(), key=lambda x: x["quoted_value"], reverse=True)
    return {
        "agents": result,
        "conversion_probability": CONVERSION_PROBABILITY,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/pipeline")
def pipeline_report(
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall pipeline value: total quoted, predicted, won, plus funnel drop-off."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)

    leads = q.all()
    total_leads = len(leads)
    quoted_value = sum(l.quote_amount or 0 for l in leads)
    won_value = sum((l.quote_amount or 0) for l in leads if l.conversion_status == "CONVERTED")
    open_quoted = sum((l.quote_amount or 0) for l in leads if l.conversion_status not in ("CONVERTED", "LOST"))
    predicted_value = round(open_quoted * CONVERSION_PROBABILITY, 2)

    return {
        "total_leads": total_leads,
        "quoted_value": round(quoted_value, 2),
        "open_quoted_value": round(open_quoted, 2),
        "predicted_value": predicted_value,
        "won_value": round(won_value, 2),
        "conversion_probability": CONVERSION_PROBABILITY,
    }


@router.get("/funnel")
def funnel_report(
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Funnel drop-off: counts per stage + % lost from previous stage."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)

    leads = q.all()
    stages = ["NEW", "REVIEWED", "QUALIFIED", "SENT", "CONTACTED", "CONVERTED"]
    counts = {s: 0 for s in stages}
    for lead in leads:
        st = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
        if st in counts:
            counts[st] += 1

    funnel = []
    prev = None
    for stage in stages:
        c = counts[stage]
        dropoff = None
        if prev is not None and prev > 0:
            dropoff = round((prev - c) / prev * 100, 1) if c <= prev else 0
        funnel.append({"stage": stage, "count": c, "dropoff_pct": dropoff, "prev": prev})
        prev = c

    return {"funnel": funnel}
