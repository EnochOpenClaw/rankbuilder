"""
RankBuilder CRM — Lead Deduplication Helper
===========================================
Detects duplicate leads before creation and merges new info into the
existing lead instead of creating a duplicate.

Strategy
--------
- Primary match: same client + same contact_email (case-insensitive)
- Secondary match: same client + same contact_phone (normalized)
- If a match is found, merge any new non-empty fields into the existing
  lead, log the merge in lead history, and return the existing lead.

Usage
-----
    from backend.dedupe import find_duplicate, merge_duplicate
    existing = find_duplicate(db, client_id, email, phone)
    if existing:
        lead, created = merge_duplicate(db, existing, new_fields, source)
    else:
        # create new lead
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.database import Lead, LeadHistory

log = logging.getLogger("crm.dedupe")


def normalize_phone(phone: str) -> str:
    """Normalize a phone number for comparison: strip non-digits, drop leading 0/27."""
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if digits.startswith("27") and len(digits) > 9:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) > 9:
        digits = digits[1:]
    return digits


def find_duplicate(
    db: Session,
    client_id: str,
    email: str = None,
    phone: str = None,
) -> Lead:
    """
    Find an existing lead in the same client that matches by email or phone.
    Returns the existing Lead, or None if no match.
    """
    if not email and not phone:
        return None

    # Primary: email match (case-insensitive)
    if email:
        existing = (
            db.query(Lead)
            .filter(
                Lead.client_id == client_id,
                Lead.contact_email.ilike(email.strip()),
            )
            .first()
        )
        if existing:
            return existing

    # Secondary: phone match (normalized)
    if phone:
        norm = normalize_phone(phone)
        if norm:
            # Fetch candidate leads with a phone and compare normalized
            candidates = (
                db.query(Lead)
                .filter(
                    Lead.client_id == client_id,
                    Lead.contact_phone.isnot(None),
                    Lead.contact_phone != "",
                )
                .all()
            )
            for cand in candidates:
                if normalize_phone(cand.contact_phone) == norm:
                    return cand

    return None


def merge_duplicate(
    db: Session,
    existing: Lead,
    new_fields: dict,
    source: str = "system",
) -> tuple[Lead, bool]:
    """
    Merge new non-empty fields into an existing lead (duplicate).
    Logs the merge in lead history. Returns (lead, created=False).
    """
    changes = []
    for field, value in new_fields.items():
        if value is None or value == "":
            continue
        current = getattr(existing, field, None)
        # Only update if the new value differs and the existing is empty
        if current is None or current == "":
            setattr(existing, field, value)
            changes.append((field, str(current), str(value)))
        elif str(current).strip().lower() != str(value).strip().lower():
            # Existing has a value; keep it but note the duplicate attempt
            changes.append((field, str(current), f"{value} (duplicate, kept existing)"))

    if changes:
        existing.updated_at = datetime.utcnow()
        for field, old_val, new_val in changes:
            hist = LeadHistory(
                lead_id=existing.id,
                field_changed=f"dedupe:{field}",
                old_value=old_val,
                new_value=new_val,
                changed_by=source,
            )
            db.add(hist)
        db.commit()
        db.refresh(existing)
        log.info(f"Duplicate lead merged into {existing.id} ({len(changes)} field(s))")

    return existing, False
