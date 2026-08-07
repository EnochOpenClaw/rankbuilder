"""
RankBuilder CRM — Dashboard API Route
GET /api/dashboard/summary — aggregated stats for a client
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db, Lead, LeadSource, LeadStatus, LeadType, User
from backend.schemas import (
    DashboardSummary,
    SourceBreakdown,
    LeadsOverTime,
    FunnelStage,
    DashboardResponse,
)
from backend.routes.auth import get_current_user, enforce_client_scope

router = APIRouter()


@router.get("/summary", response_model=DashboardResponse)
def dashboard_summary(
    client_id: str = Query(..., description="Client ID to show dashboard for"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated stats for a client's leads (scoped to user's client)."""
    effective_client_id = enforce_client_scope(client_id, current_user)

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Base filtered query
    base = db.query(Lead).filter(
        Lead.client_id == effective_client_id,
        Lead.created_at >= cutoff,
    )

    # Counts
    total = base.count()
    qualified = base.filter(Lead.lead_type == LeadType.VALID).count()
    sent = base.filter(Lead.status.in_([LeadStatus.SENT, LeadStatus.CONTACTED,
                                        LeadStatus.CONVERTED])).count()
    converted = base.filter(Lead.conversion_status == "CONVERTED").count()
    lost = base.filter(Lead.conversion_status == "LOST").count()

    # Rates
    qualification_rate = round((qualified / total * 100), 1) if total > 0 else 0.0
    conversion_rate = round((converted / qualified * 100), 1) if qualified > 0 else 0.0

    # Avg response time (NEW → SENT) with percentiles
    sent_leads = db.query(Lead).filter(
        Lead.client_id == client_id,
        Lead.sent_to_client_at.isnot(None),
        Lead.created_at >= cutoff,
    ).all()

    if sent_leads:
        diffs = sorted([
            (l.sent_to_client_at - l.created_at).total_seconds() / 3600
            for l in sent_leads
        ])
        n = len(diffs)
        avg_response_time = round(sum(diffs) / n, 1)
        p50_idx = int(n * 0.50)
        p95_idx = int(n * 0.95)
        p50_response_time = round(diffs[p50_idx], 1)
        p95_response_time = round(diffs[p95_idx], 1)
    else:
        avg_response_time = None
        p50_response_time = None
        p95_response_time = None

    summary = DashboardSummary(
        total_leads=total,
        qualified_leads=qualified,
        sent_to_client=sent,
        converted=converted,
        lost=lost,
        qualification_rate=qualification_rate,
        conversion_rate=conversion_rate,
        avg_response_time_hours=avg_response_time,
        p50_response_time_hours=p50_response_time,
        p95_response_time_hours=p95_response_time,
    )

    # Source breakdown
    source_rows = (
        db.query(Lead.source, func.count(Lead.id).label("count"))
        .filter(Lead.client_id == client_id, Lead.created_at >= cutoff)
        .group_by(Lead.source)
        .all()
    )

    source_breakdown = []
    for row in source_rows:
        qualified_count = (
            db.query(func.count(Lead.id))
            .filter(
                Lead.client_id == client_id,
                Lead.source == row[0],
                Lead.lead_type == LeadType.VALID,
                Lead.created_at >= cutoff,
            )
            .scalar()
        )
        # Per-source response time
        src_sent_leads = db.query(Lead).filter(
            Lead.client_id == client_id,
            Lead.source == row[0],
            Lead.sent_to_client_at.isnot(None),
            Lead.created_at >= cutoff,
        ).all()
        if src_sent_leads:
            src_diffs = [(l.sent_to_client_at - l.created_at).total_seconds() / 3600 for l in src_sent_leads]
            src_avg_rt = round(sum(src_diffs) / len(src_diffs), 1)
            src_sent_count = len(src_sent_leads)
        else:
            src_avg_rt = None
            src_sent_count = 0
        source_breakdown.append(
            SourceBreakdown(
                source=row[0].value if hasattr(row[0], "value") else str(row[0]),
                count=row[1],
                qualified_count=qualified_count or 0,
                avg_response_time_hours=src_avg_rt,
                leads_sent=src_sent_count,
            )
        )

    # Leads over time (daily)
    date_rows = (
        db.query(
            func.date(Lead.created_at).label("date"),
            func.count(Lead.id).label("count"),
        )
        .filter(Lead.client_id == client_id, Lead.created_at >= cutoff)
        .group_by(func.date(Lead.created_at))
        .order_by(func.date(Lead.created_at))
        .all()
    )

    leads_over_time = [
        LeadsOverTime(date=str(r.date), count=r.count)
        for r in date_rows
    ]

    # Funnel — count leads at each pipeline stage (status)
    funnel_stages = [
        ("New", LeadStatus.NEW),
        ("Reviewed", LeadStatus.REVIEWED),
        ("Qualified", LeadStatus.QUALIFIED),
        ("Sent", LeadStatus.SENT),
        ("Contacted", LeadStatus.CONTACTED),
        ("Converted", LeadStatus.CONVERTED),
        ("Lost", LeadStatus.LOST),
    ]
    funnel = []
    for label, status in funnel_stages:
        count = (
            db.query(func.count(Lead.id))
            .filter(
                Lead.client_id == client_id,
                Lead.created_at >= cutoff,
                Lead.status == status,
            )
            .scalar()
            or 0
        )
        funnel.append(FunnelStage(stage=label, count=count))

    return DashboardResponse(
        summary=summary,
        source_breakdown=source_breakdown,
        leads_over_time=leads_over_time,
        funnel=funnel,
    )
