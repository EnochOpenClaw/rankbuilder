"""
RankBuilder CRM — Lead Assignment Logic
=======================================
Auto-assigns leads to sales reps based on region (location).

Rules (configured via env or defaults):
  - Johannesburg region  → Tiaan  (tiaan@houseofsupreme.co.za)
  - Cape Town region     → Richard (richard@houseofsupreme.co.za)
  - All other regions    → Craig (craig@houseofsupreme.co.za)

Also provides follow-up tracking helpers used by the /api/leads/{id}/follow-up
endpoint and logged to the LeadHistory timeline for productivity reporting.
"""

import os
import re
from datetime import datetime, timedelta

from backend.database import Lead, LeadHistory

# ── Region → rep mapping (email is the stable key) ───────────────────────────
DEFAULT_REP = os.environ.get("ASSIGN_DEFAULT_REP", "craig@houseofsupreme.co.za")
DEFAULT_REP_NAME = os.environ.get("ASSIGN_DEFAULT_REP_NAME", "Craig Pauls")

# Johannesburg region — expanded list of suburbs/areas in Gauteng/JHB metro
JOHANNESBURG_KEYWORDS = [
    "johannesburg", "joburg", "jhb", "jozi", "gauteng", "sandton",
    "randburg", "midrand", "centurion", "pretoria", "roodepoort",
    "krugersdorp", "kempton park", "benoni", "boksburg", "brakpan",
    "springs", "germiston", "alberton", "vanderbijlpark", "vereeniging",
    "soweto", "alexandra", "rosebank", "melrose", "parktown", "fourways",
    "bryanston", "kew", "northcliff", "roodepoort", "east rand", "west rand",
    "north riding", "randpark", "greenside", "emmarentia", "craighall",
    "hyde park", "illovo", "houghton", "kensington", "bedfordview",
    "eastgate", "linden", "melville", "parkview", "westcliff", "zoo lake",
]

# Cape Town region — Western Cape / Cape Town metro
CAPE_TOWN_KEYWORDS = [
    "cape town", "cpt", "western cape", "wc", "stellenbosch", "paarl",
    "somerset west", "bellville", "parow", "goodwood", "milnerton",
    "claremont", "rondebosch", "wynberg", "constantia", "hout bay",
    "noordhoek", "muizenberg", "fish hoek", "simon", "tokai", "newlands",
    "obs", "observatory", "seapoint", "sea point", "green point", "camps bay",
    "blouberg", "durbanville", "kraaifontein", "kuils river", "brackenfell",
    "gordons bay", "strand", "franschhoek", "worcester", "george", "knysna",
]


def _norm(s: str) -> str:
    """Normalize a location string for matching."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _contains_keywords(location: str, keywords: list) -> bool:
    norm = _norm(location)
    if not norm:
        return False
    for kw in keywords:
        if kw in norm:
            return True
    return False


def resolve_rep_for_location(location: str) -> tuple:
    """
    Return (rep_email, rep_name) for a given lead location string.
    Falls back to the default rep (Craig) for unrecognised regions.
    """
    loc = location or ""
    if _contains_keywords(loc, JOHANNESBURG_KEYWORDS):
        return (
            os.environ.get("ASSIGN_JHB_REP", "tiaan@houseofsupreme.co.za"),
            os.environ.get("ASSIGN_JHB_REP_NAME", "Tiaan"),
        )
    if _contains_keywords(loc, CAPE_TOWN_KEYWORDS):
        return (
            os.environ.get("ASSIGN_CPT_REP", "richard@houseofsupreme.co.za"),
            os.environ.get("ASSIGN_CPT_REP_NAME", "Richard"),
        )
    return (DEFAULT_REP, DEFAULT_REP_NAME)


def assign_lead(db, lead: Lead, changed_by: str = "system") -> bool:
    """
    Auto-assign a lead based on its location. Returns True if assignment changed.
    Records the assignment in LeadHistory for the timeline.
    """
    rep_email, rep_name = resolve_rep_for_location(lead.location)

    if lead.assigned_to == rep_email:
        return False  # already assigned to this rep

    old_rep = lead.assigned_to
    lead.assigned_to = rep_email
    lead.assigned_to_name = rep_name
    lead.assigned_at = datetime.utcnow()
    # Fresh assignment → clear read state so the rep sees the new lead highlighted
    lead.read_at = None
    lead.read_by = None

    hist = LeadHistory(
        lead_id=lead.id,
        field_changed="assigned_to",
        old_value=old_rep or "",
        new_value=f"{rep_name} <{rep_email}>",
        changed_by=changed_by,
    )
    db.add(hist)
    return True


def log_follow_up(db, lead: Lead, note: str, changed_by: str = "system",
                  activity_type: str = "CALL", outcome: str = None,
                  occurred_at: datetime = None) -> dict:
    """
    Log a follow-up action on a lead. Increments follow_up_count, updates
    last_follow_up_at, and records a stacked LeadActivity row so every attempt
    (e.g. called 08:00 no answer, called 10:00 no answer) is preserved on the
    timeline.

    Returns a dict with the updated counters for the response.
    """
    from backend.database import LeadActivity
    from datetime import datetime as _dt
    now = _dt.utcnow()
    occurred = occurred_at or now

    lead.follow_up_count = (lead.follow_up_count or 0) + 1
    lead.last_follow_up_at = occurred
    lead.reminder_stage = 0  # a fresh follow-up resets the escalation ladder

    # Stacked activity row — one per attempt, never overwritten
    activity = LeadActivity(
        lead_id=lead.id,
        activity_type=activity_type,
        outcome=outcome,
        note=note or "Follow-up logged",
        occurred_at=occurred,
        created_by=changed_by,
    )
    db.add(activity)

    hist = LeadHistory(
        lead_id=lead.id,
        field_changed="follow_up",
        old_value=None,
        new_value=note or "Follow-up logged",
        changed_by=changed_by,
    )
    db.add(hist)
    db.commit()

    return {
        "follow_up_count": lead.follow_up_count,
        "last_follow_up_at": lead.last_follow_up_at.isoformat() if lead.last_follow_up_at else None,
    }


def due_for_follow_up(lead: Lead, hours: int = 24) -> bool:
    """Return True if the lead has no follow-up yet, or the last follow-up is older than `hours`."""
    if not lead.last_follow_up_at:
        return True
    return (datetime.utcnow() - lead.last_follow_up_at) >= timedelta(hours=hours)
