"""
RankBuilder CRM — Dashboard API Route
GET /api/dashboard/summary — aggregated stats for a client
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db, Lead, LeadSource, LeadStatus, LeadType
from backend.schemas import (
    DashboardSummary,
    SourceBreakdown,
    LeadsOverTime,
    DashboardResponse,
)

router = APIRouter()


@router.get("/summary", response_model=DashboardResponse)
def dashboard_summary(
    client_id: str = Query(..., description="Client ID to show dashboard for"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: Session = Depends(get_db),
):
    """Aggregated stats for a client's leads."""

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Base filtered query
    base = db.query(Lead).filter(
        Lead.client_id == client_id,
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

    # Avg response time (NEW → SENT)
    sent_leads = db.query(Lead).filter(
        Lead.client_id == client_id,
        Lead.sent_to_client_at.isnot(None),
        Lead.created_at >= cutoff,
    ).all()

    if sent_leads:
        diffs = [
            (l.sent_to_client_at - l.created_at).total_seconds() / 3600
            for l in sent_leads
        ]
        avg_response_time = round(sum(diffs) / len(diffs), 1)
    else:
        avg_response_time = None

    summary = DashboardSummary(
        total_leads=total,
        qualified_leads=qualified,
        sent_to_client=sent,
        converted=converted,
        lost=lost,
        qualification_rate=qualification_rate,
        conversion_rate=conversion_rate,
        avg_response_time_hours=avg_response_time,
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
        source_breakdown.append(
            SourceBreakdown(
                source=row[0].value if hasattr(row[0], "value") else str(row[0]),
                count=row[1],
                qualified_count=qualified_count or 0,
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

    return DashboardResponse(
        summary=summary,
        source_breakdown=source_breakdown,
        leads_over_time=leads_over_time,
    )
