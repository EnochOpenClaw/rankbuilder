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

from backend.database import get_db, Lead, LeadActivity, User, UserRole
from backend.routes.auth import get_current_user, enforce_client_scope

router = APIRouter()

# Conversion probability for predicted sales (quotes sent = high intent, they've met the client)
CONVERSION_PROBABILITY = 0.5  # 50% — quoted leads are more likely to close


def _apply_date_range(q, date_from: Optional[str], date_to: Optional[str]):
    """Filter leads by created_at date range (ISO dates YYYY-MM-DD)."""
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(Lead.created_at >= d)
        except ValueError:
            pass
    if date_to:
        try:
            # Inclusive of the end date
            d = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(Lead.created_at < d)
        except ValueError:
            pass
    return q


@router.get("/agent")
def agent_sales_report(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD (lead created)"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD (lead created)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-agent sales report — leads, quoted, won, lost, quoted value, predicted value."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)

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
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall pipeline value: total quoted, predicted, won, plus funnel drop-off."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)

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
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Funnel drop-off: counts per stage + % lost from previous stage."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)

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


@router.get("/source-roi")
def source_roi_report(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Source ROI — per source: leads, quoted, converted, conv rate, quoted value, won value."""
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)

    leads = q.all()
    sources = {}

    for lead in leads:
        src = lead.source.value if hasattr(lead.source, "value") else str(lead.source or "UNKNOWN")
        if src not in sources:
            sources[src] = {"source": src, "leads": 0, "quoted": 0, "converted": 0, "lost": 0, "quoted_value": 0.0, "won_value": 0.0}
        s = sources[src]
        s["leads"] += 1
        qa = lead.quote_amount or 0

        if lead.conversion_status == "CONVERTED":
            s["converted"] += 1
            if qa > 0:
                s["quoted"] += 1
                s["quoted_value"] += qa
            s["won_value"] += qa
        elif lead.conversion_status == "LOST":
            s["lost"] += 1
            if qa > 0:
                s["quoted"] += 1
                s["quoted_value"] += qa
        else:
            if qa > 0:
                s["quoted"] += 1
                s["quoted_value"] += qa

    result = list(sources.values())
    for s in result:
        s["conversion_rate"] = round(s["converted"] / s["leads"] * 100, 1) if s["leads"] else 0.0
        s["avg_deal_value"] = round(s["won_value"] / s["converted"], 2) if s["converted"] else 0.0

    # Sort by won_value desc
    result.sort(key=lambda x: x["won_value"], reverse=True)
    return {"sources": result}


@router.get("/response-time")
def response_time_report(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lead response-time report.

    For each lead, response time = first logged activity (follow-up call/email/etc)
    minus lead creation time. Aggregated per agent + overall (avg + median, in hours).
    Leads with no activity are counted as 'no response yet'.
    """
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)
    leads = q.all()

    # First-activity time per lead (one query)
    first_activity = {}
    if leads:
        ids = [l.id for l in leads]
        acts = (
            db.query(LeadActivity.lead_id, func.min(LeadActivity.occurred_at))
            .filter(LeadActivity.lead_id.in_(ids))
            .group_by(LeadActivity.lead_id)
            .all()
        )
        first_activity = {aid: t for aid, t in acts}

    from statistics import median
    agents = {}
    all_responses = []
    no_response = 0

    for lead in leads:
        agent_email = lead.assigned_to or "unassigned"
        agent_name = lead.assigned_to_name or ("Unassigned" if agent_email == "unassigned" else agent_email)
        if agent_email not in agents:
            agents[agent_email] = {
                "email": agent_email,
                "name": agent_name,
                "leads": 0,
                "responded": 0,
                "no_response": 0,
                "response_times_hours": [],
            }
        a = agents[agent_email]
        a["leads"] += 1

        created = lead.created_at
        first = first_activity.get(lead.id)
        if created and first:
            hours = (first - created).total_seconds() / 3600.0
            if hours >= 0:
                a["responded"] += 1
                a["response_times_hours"].append(hours)
                all_responses.append(hours)
                continue
        a["no_response"] += 1
        no_response += 1

    result = []
    for a in agents.values():
        times = sorted(a["response_times_hours"])
        result.append({
            "email": a["email"],
            "name": a["name"],
            "leads": a["leads"],
            "responded": a["responded"],
            "no_response": a["no_response"],
            "response_rate": round(a["responded"] / a["leads"] * 100, 1) if a["leads"] else 0.0,
            "avg_response_hours": round(sum(times) / len(times), 2) if times else None,
            "median_response_hours": round(median(times), 2) if times else None,
            "fastest_response_hours": round(times[0], 2) if times else None,
            "slowest_response_hours": round(times[-1], 2) if times else None,
        })

    result.sort(key=lambda x: (x["avg_response_hours"] is None, x["avg_response_hours"] or float("inf")))
    all_times = sorted(all_responses)
    return {
        "agents": result,
        "overall": {
            "leads": len(leads),
            "responded": len(all_responses),
            "no_response": no_response,
            "response_rate": round(len(all_responses) / len(leads) * 100, 1) if leads else 0.0,
            "avg_response_hours": round(sum(all_times) / len(all_times), 2) if all_times else None,
            "median_response_hours": round(median(all_times), 2) if all_times else None,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/activity")
def activity_report(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activity / follow-up volume report.

    Per agent (by who logged the activity): total follow-up attempts, breakdown
    by type (CALL/EMAIL/WHATSAPP/SMS/NOTE/OTHER) and by outcome, plus distinct
    leads worked. Shows effort, not just results.
    """
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)
    leads = q.all()
    lead_ids = [l.id for l in leads]

    agents = {}
    type_totals = {}
    outcome_totals = {}
    total_activities = 0
    total_leads_worked = set()

    if lead_ids:
        acts = (
            db.query(LeadActivity)
            .filter(LeadActivity.lead_id.in_(lead_ids))
            .all()
        )
        for act in acts:
            who = act.created_by or "unknown"
            if who not in agents:
                agents[who] = {
                    "email": who,
                    "name": who,
                    "total": 0,
                    "leads_worked": set(),
                    "by_type": {},
                    "by_outcome": {},
                }
            a = agents[who]
            a["total"] += 1
            a["leads_worked"].add(act.lead_id)
            t = act.activity_type or "OTHER"
            a["by_type"][t] = a["by_type"].get(t, 0) + 1
            type_totals[t] = type_totals.get(t, 0) + 1
            o = act.outcome or "NO_OUTCOME"
            a["by_outcome"][o] = a["by_outcome"].get(o, 0) + 1
            outcome_totals[o] = outcome_totals.get(o, 0) + 1
            total_activities += 1
            total_leads_worked.add(act.lead_id)

    # Resolve display names from users table where possible
    users = {u.email: u.full_name for u in db.query(User).all() if u.email}
    result = []
    for email, a in agents.items():
        result.append({
            "email": email,
            "name": users.get(email) or email,
            "total": a["total"],
            "leads_worked": len(a["leads_worked"]),
            "by_type": a["by_type"],
            "by_outcome": a["by_outcome"],
        })
    result.sort(key=lambda x: x["total"], reverse=True)

    return {
        "agents": result,
        "overall": {
            "total_activities": total_activities,
            "leads_worked": len(total_leads_worked),
            "by_type": type_totals,
            "by_outcome": outcome_totals,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/funnel-trend")
def funnel_trend_report(
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    bucket: str = Query("week", description="week | month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conversion funnel trend over time.

    Groups leads into weekly/monthly buckets (by created_at) and reports, per
    bucket: total leads, how many reached key stages (QUALIFIED/CONTACTED), and
    conversion rate — so you can see whether conversion is improving or slipping.
    """
    effective_client_id = enforce_client_scope(client_id, current_user)
    q = db.query(Lead)
    if effective_client_id:
        q = q.filter(Lead.client_id == effective_client_id)
    q = _apply_date_range(q, date_from, date_to)
    leads = q.all()

    def bucket_key(dt):
        if not dt:
            return None
        if bucket == "month":
            return dt.strftime("%Y-%m")
        # ISO week: (year, week)
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    buckets = {}
    for lead in leads:
        key = bucket_key(lead.created_at)
        if not key:
            continue
        if key not in buckets:
            buckets[key] = {"period": key, "leads": 0, "qualified": 0, "contacted": 0, "converted": 0}
        b = buckets[key]
        b["leads"] += 1
        st = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
        if st in ("QUALIFIED", "SENT", "CONTACTED", "CONVERTED"):
            b["qualified"] += 1
        if st in ("CONTACTED", "CONVERTED"):
            b["contacted"] += 1
        if lead.conversion_status == "CONVERTED":
            b["converted"] += 1

    result = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        result.append({
            "period": key,
            "leads": b["leads"],
            "qualified": b["qualified"],
            "contacted": b["contacted"],
            "converted": b["converted"],
            "qualification_rate": round(b["qualified"] / b["leads"] * 100, 1) if b["leads"] else 0.0,
            "contact_rate": round(b["contacted"] / b["leads"] * 100, 1) if b["leads"] else 0.0,
            "conversion_rate": round(b["converted"] / b["leads"] * 100, 1) if b["leads"] else 0.0,
        })

    return {"buckets": result, "bucket": bucket, "generated_at": datetime.utcnow().isoformat()}
