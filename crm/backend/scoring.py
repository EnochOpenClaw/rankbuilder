"""
RankBuilder CRM — Lead Scoring Engine

Computes an automated quality score (1-100) for a lead based on configurable
rules stored in the `scoring_rules` table. Rules are SYSTEM_ADMIN managed and
can be global (client_id NULL) or per-client.

Score tiers:
  - Hot  (>= 70): high-intent, route to agent immediately
  - Warm (40-69): nurture / follow-up
  - Cold (< 40): review queue / low priority
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import ScoringRule, Lead


# ── Rule evaluation ─────────────────────────────────────────────────────────

def _eval_rule(lead: Lead, rule: ScoringRule) -> bool:
    """Evaluate a single scoring rule against a lead. Returns True if it matches."""
    field = rule.field
    op = rule.operator
    value = rule.value

    # Resolve the field value from the lead
    if field == "source":
        actual = lead.source.value if hasattr(lead.source, "value") else str(lead.source or "")
    elif field == "has_phone":
        actual = bool(lead.contact_phone and str(lead.contact_phone).strip())
    elif field == "has_website":
        actual = bool(lead.company_website and str(lead.company_website).strip())
    elif field == "has_email":
        actual = bool(lead.contact_email and str(lead.contact_email).strip())
    elif field == "no_email":
        actual = not (lead.contact_email and str(lead.contact_email).strip())
    elif field == "lead_type":
        actual = lead.lead_type.value if hasattr(lead.lead_type, "value") else str(lead.lead_type or "")
    elif field == "location":
        actual = (lead.location or "").lower()
    elif field == "message_keyword":
        actual = ((lead.message_excerpt or "") + " " + (lead.source_query or "")).lower()
    elif field == "age_days":
        # Days since lead created
        created = lead.created_at
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            actual = (datetime.now(timezone.utc) - created).days
        else:
            actual = 0
    else:
        return False

    # Apply operator
    if op == "eq":
        return str(actual).lower() == str(value or "").lower()
    if op == "ne":
        return str(actual).lower() != str(value or "").lower()
    if op == "contains":
        return str(value or "").lower() in str(actual).lower()
    if op == "is_true":
        return bool(actual)
    if op == "is_false":
        return not bool(actual)
    if op in ("gt", "lt"):
        try:
            a = float(actual)
            v = float(value)
            return a > v if op == "gt" else a < v
        except (TypeError, ValueError):
            return False
    return False


def compute_score(lead: Lead, db: Session) -> int:
    """Compute the automated quality score (0-100) for a lead by summing matching rules."""
    # Load applicable rules: global (client_id NULL) + this lead's client
    rules = (
        db.query(ScoringRule)
        .filter(ScoringRule.is_active == 1)
        .filter(
            (ScoringRule.client_id.is_(None)) |
            (ScoringRule.client_id == lead.client_id)
        )
        .all()
    )

    total = 0
    for rule in rules:
        if _eval_rule(lead, rule):
            total += rule.points

    # Clamp to 0-100
    return max(0, min(100, total))


def score_tier(score: int) -> str:
    """Return the tier label for a score."""
    if score >= 70:
        return "HOT"
    if score >= 40:
        return "WARM"
    return "COLD"


# ── Default rules (seeded on first run) ─────────────────────────────────────

DEFAULT_RULES = [
    # Source-based
    {"field": "source", "operator": "eq", "value": "HARO", "points": 30},
    {"field": "source", "operator": "eq", "value": "CONNECTIVELY", "points": 25},
    {"field": "source", "operator": "eq", "value": "GUEST_OUTREACH", "points": 20},
    {"field": "source", "operator": "eq", "value": "WEBSITE", "points": 25},
    {"field": "source", "operator": "eq", "value": "WHATSAPP", "points": 20},
    {"field": "source", "operator": "eq", "value": "CALL_IN", "points": 20},
    {"field": "source", "operator": "eq", "value": "FACEBOOK", "points": 10},
    {"field": "source", "operator": "eq", "value": "PPC", "points": 15},
    {"field": "source", "operator": "eq", "value": "WORD_OF_MOUTH", "points": 15},
    {"field": "source", "operator": "eq", "value": "MANUAL", "points": 10},
    # Contact completeness
    {"field": "has_phone", "operator": "is_true", "value": None, "points": 10},
    {"field": "has_website", "operator": "is_true", "value": None, "points": 5},
    {"field": "has_email", "operator": "is_true", "value": None, "points": 5},
    {"field": "no_email", "operator": "is_true", "value": None, "points": -10},
    # Lead type
    {"field": "lead_type", "operator": "eq", "value": "VALID", "points": 15},
    {"field": "lead_type", "operator": "eq", "value": "FOLLOW_UP", "points": 10},
    {"field": "lead_type", "operator": "eq", "value": "INVALID", "points": -30},
    # Message keywords (high-intent)
    {"field": "message_keyword", "operator": "contains", "value": "quote", "points": 10},
    {"field": "message_keyword", "operator": "contains", "value": "shutter", "points": 10},
    {"field": "message_keyword", "operator": "contains", "value": "blind", "points": 10},
    {"field": "message_keyword", "operator": "contains", "value": "screen", "points": 10},
    {"field": "message_keyword", "operator": "contains", "value": "install", "points": 5},
    {"field": "message_keyword", "operator": "contains", "value": "price", "points": 5},
    {"field": "message_keyword", "operator": "contains", "value": "cost", "points": 5},
    # Age penalty (leads go cold)
    {"field": "age_days", "operator": "gt", "value": "7", "points": -10},
    {"field": "age_days", "operator": "gt", "value": "14", "points": -15},
]


def seed_default_rules(db: Session):
    """Seed default scoring rules if the table is empty."""
    if db.query(ScoringRule).count() > 0:
        return
    for r in DEFAULT_RULES:
        db.add(ScoringRule(
            client_id=None,  # global rule
            field=r["field"],
            operator=r["operator"],
            value=r["value"],
            points=r["points"],
            is_active=1,
        ))
    db.commit()
