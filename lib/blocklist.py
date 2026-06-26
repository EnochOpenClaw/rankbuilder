#!/usr/bin/env python3
"""
Blocklist Manager for RankBuilder Outreach
Handles blacklist (spam/solicitors) and buyers list (positive leads).
Both lists checked before composing/sending outreach.
"""

import json
import re
from pathlib import Path
from typing import Optional

BLOCKED_DIR = Path(__file__).parent.parent / "blocked"
BLACKLIST_FILE = BLOCKED_DIR / "blacklist.json"
BUYERS_FILE = BLOCKED_DIR / "buyers.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {"_schema": path.stem + "-v1", "blocked": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"_schema": path.stem + "-v1", "blocked": []}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_email(email: str) -> str:
    """Lowercase and strip whitespace for consistent matching."""
    return email.lower().strip()


def is_blocked(email: str) -> bool:
    """Check if an email address is on the blacklist."""
    data = _load_json(BLACKLIST_FILE)
    blocked_emails = {normalize_email(entry["email"]) for entry in data.get("blocked", [])}
    return normalize_email(email) in blocked_emails


def block_email(email: str, reason: str, source: str = "unknown") -> dict:
    """Add an email to the blacklist."""
    data = _load_json(BLACKLIST_FILE)
    entry = {
        "email": normalize_email(email),
        "reason": reason,
        "source": source,
        "added": _today(),
    }
    # Avoid duplicates
    emails = {e["email"] for e in data["blocked"]}
    if entry["email"] not in emails:
        data["blocked"].append(entry)
        _save_json(BLACKLIST_FILE, data)
    return entry


def unblock_email(email: str) -> bool:
    """Remove an email from the blacklist. Returns True if found and removed."""
    data = _load_json(BLACKLIST_FILE)
    original = len(data["blocked"])
    data["blocked"] = [
        e for e in data["blocked"] if normalize_email(e["email"]) != normalize_email(email)
    ]
    if len(data["blocked"]) < original:
        _save_json(BLACKLIST_FILE, data)
        return True
    return False


def is_buyer(email: str) -> bool:
    """Check if an email address is a confirmed buyer lead."""
    data = _load_json(BUYERS_FILE)
    buyer_emails = {normalize_email(entry["email"]) for entry in data.get("buyers", [])}
    return normalize_email(email) in buyer_emails


def add_buyer(
    email: str,
    note: str = "",
    source: str = "reply_to_pitch",
    company: str = "",
) -> dict:
    """Flag an email as a positive buyer lead (replied with genuine interest)."""
    data = _load_json(BUYERS_FILE)
    entry = {
        "email": normalize_email(email),
        "note": note,
        "source": source,
        "company": company,
        "added": _today(),
    }
    emails = {e["email"] for e in data["buyers"]}
    if entry["email"] not in emails:
        data["buyers"].append(entry)
        _save_json(BUYERS_FILE, data)
    return entry


def list_blocked() -> list:
    """Return full blacklist."""
    return _load_json(BLACKLIST_FILE).get("blocked", [])


def list_buyers() -> list:
    """Return full buyers list."""
    return _load_json(BUYERS_FILE).get("buyers", [])


def _today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# CLI interface for quick management
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: blocklist.py <block|unblock|check|list|buyers|add-buyer> [args]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check" and len(sys.argv) >= 3:
        email = sys.argv[2]
        if is_blocked(email):
            print(f"🚫 BLOCKED: {email}")
        elif is_buyer(email):
            print(f"💬 BUYER: {email}")
        else:
            print(f"✅ CLEAN: {email}")

    elif cmd == "block" and len(sys.argv) >= 4:
        email, reason = sys.argv[2], sys.argv[3]
        result = block_email(email, reason, source="cli")
        print(f"🚫 Blocked: {email} — {reason}")

    elif cmd == "unblock" and len(sys.argv) >= 3:
        email = sys.argv[2]
        if unblock_email(email):
            print(f"✅ Unblocked: {email}")
        else:
            print(f"Not found: {email}")

    elif cmd == "list":
        for e in list_blocked():
            print(f"  🚫 {e['email']} | {e['reason']} | {e.get('source','?')} | {e.get('added','?')}")

    elif cmd == "buyers":
        for e in list_buyers():
            print(f"  💬 {e['email']} | {e.get('note','')} | {e.get('company','')} | {e.get('added','?')}")

    elif cmd == "add-buyer" and len(sys.argv) >= 3:
        email = sys.argv[2]
        note = sys.argv[3] if len(sys.argv) >= 4 else ""
        add_buyer(email, note=note)
        print(f"💬 Added buyer: {email}")

    else:
        print("Unknown command or missing args")
        sys.exit(1)
