"""
RankBuilder CRM — Python API Client
All RankBuilder agents use this to talk to the CRM backend.
Handles auth, lead creation, and status updates.

Usage:
    from lib.crm_client import CRMLead, create_lead, update_lead, get_client_id

Environment variables (set in credentials.json or OS env):
    CRM_API_URL  — e.g. "http://localhost:8001"
    CRM_API_TOKEN — Bearer token for the service account
    CRM_CLIENT_ID — Default client ID for this installation
                     (House of Supreme = e74119b9-17e3-4f74-b218-67ef0e66f1cc)
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────

# Fixed path — all RankBuilder scripts are under this root
# Resolve relative to this file so it works both locally and inside the
# Docker container (/app/lib/crm_client.py → /app). Falls back to the
# local workspace path if __file__ is unavailable.
RANKBUILDER_ROOT = Path(__file__).resolve().parent.parent
if str(RANKBUILDER_ROOT) == "/app":
    pass  # container path is correct
# Override with env if set (allows deployment-specific roots)
RANKBUILDER_ROOT = Path(
    os.environ.get("RANKBUILDER_ROOT", str(RANKBUILDER_ROOT))
)

def _find_credentials() -> Path:
    """
    Locate credentials.json.
    Checks (in order):
      1. {RANKBUILDER_ROOT}/lib/credentials.json   (primary — lib/ beside this file)
      2. {RANKBUILDER_ROOT}/credentials.json        (workspace root)
      3. ./credentials.json                         (CWD — for cron/VPS portability)
    """
    candidates = [
        RANKBUILDER_ROOT / "lib" / "credentials.json",
        RANKBUILDER_ROOT / "credentials.json",
        Path.cwd() / "credentials.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # return first candidate even if missing (for error reporting)

CREDS_FILE = _find_credentials()

def _load_creds() -> dict:
    if CREDS_FILE.exists():
        try:
            return json.loads(CREDS_FILE.read_text())
        except Exception:
            pass
    return {}

_CREDS = _load_creds()
_CRM_CREDS = _CREDS.get("crm", {})  # nested under "crm" key

CRM_API_URL   = os.environ.get("CRM_API_URL")   or _CRM_CREDS.get("api_url", "http://localhost:8001")
CRM_API_TOKEN = os.environ.get("CRM_API_TOKEN") or _CRM_CREDS.get("api_token", "")
CRM_CLIENT_ID = os.environ.get("CRM_CLIENT_ID") or _CRM_CREDS.get("client_id", "")

# ── Logging ────────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [CRM] [{level}] {msg}")

def log_error(msg: str):
    log(msg, "ERROR")

def log_debug(msg: str):
    log(msg, "DEBUG")


# ── Low-level request ─────────────────────────────────────────────────────────

class CRMError(Exception):
    """CRM API error with context."""
    def __init__(self, message: str, status_code: int = None, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _api_request(method: str, path: str, body: dict = None, authenticated: bool = True) -> dict:
    """
    Make an authenticated request to the CRM API.
    CRM backend mounts routes under /api (e.g. /api/leads, /api/clients).
    /health is at the root.
    Raises CRMError on failure.
    """
    # Health endpoint is not under /api
    if path == "/health":
        url = f"{CRM_API_URL}{path}"
    else:
        url = f"{CRM_API_URL}/api{path}"
    headers = {"Content-Type": "application/json"}
    if authenticated and CRM_API_TOKEN:
        headers["Authorization"] = f"Bearer {CRM_API_TOKEN}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        raise CRMError(
            f"CRM API error {e.code} on {method} {path}: {err_body[:200]}",
            status_code=e.code,
            response_body=err_body,
        )
    except urllib.error.URLError as e:
        raise CRMError(f"CRM unreachable at {url}: {e.reason}")


# ── Convenience wrappers ──────────────────────────────────────────────────────

def get_or_create_lead(
    client_id: str = None,
    source: str = "MANUAL",
    contact_email: str = None,
    company_name: str = None,
    contact_name: str = None,
    contact_phone: str = None,
    company_website: str = None,
    message_excerpt: str = None,
    pitch_sent: str = None,
    quality_score: int = None,
    source_query: str = None,
    notes: str = None,
    campaign_id: str = None,
    lookup_email: bool = True,
) -> dict:
    """
    Find an existing lead by email OR create a new one.

    This is the main entry point for agents. If a lead for the same
    company+source already exists (by email), it returns that instead
    of creating a duplicate.

    Returns the LeadResponse dict from the CRM.
    Raises CRMError if the API call fails.
    """
    client_id = client_id or CRM_CLIENT_ID
    if not client_id:
        raise CRMError("No CRM_CLIENT_ID set — cannot create lead")

    # Try to find existing lead by email (avoid duplicates)
    if contact_email and lookup_email:
        try:
            existing = _api_request(
                "GET",
                f"/leads?client_id={urllib.parse.quote(client_id)}&contact_email={urllib.parse.quote(contact_email)}",
            )
            if existing.get("leads") and len(existing["leads"]) > 0:
                lead = existing["leads"][0]
                log_debug(f"Found existing lead {lead['id']} for {contact_email}")
                return lead
        except CRMError as e:
            log_debug(f"Lookup by email failed ({e}), creating new lead: {e}")

    # Create new lead
    payload = {
        "client_id": client_id,
        "source": source,
    }
    if campaign_id:     payload["campaign_id"] = campaign_id
    if source_query:    payload["source_query"] = source_query
    if contact_name:    payload["contact_name"] = contact_name
    if contact_email:   payload["contact_email"] = contact_email
    if contact_phone:   payload["contact_phone"] = contact_phone
    if company_name:    payload["company_name"] = company_name
    if company_website: payload["company_website"] = company_website
    if message_excerpt: payload["message_excerpt"] = message_excerpt
    if pitch_sent:      payload["pitch_sent"] = pitch_sent
    if quality_score:   payload["quality_score"] = quality_score
    if notes:           payload["notes"] = notes

    result = _api_request("POST", "/leads", body=payload)
    lead = result  # LeadResponse is returned directly
    log(f"Created lead {lead['id']} [{source}] {company_name or contact_email or '?'}")
    return lead


def update_lead(
    lead_id: str,
    status: str = None,
    lead_type: str = None,
    quality_score: int = None,
    client_response: str = None,
    notes: str = None,
    conversion_status: str = None,
    pitch_sent: str = None,
) -> dict:
    """
    Update one or more fields on an existing lead.

    Common status transitions:
      NEW → REVIEWED      (agent reviewed the lead)
      REVIEWED → QUALIFIED (lead is a real opportunity)
      QUALIFIED → SENT     (pitch sent to journalist/prospect)
      SENT → CONTACTED     (journalist/site responded)
      SENT → CONVERTED     (lead became a client/customer)
      SENT → LOST          (lead went cold)

    lead_type: VALID (good lead), INVALID (spam/wrong fit), FOLLOW_UP (needs more info)
    conversion_status: CONVERTED or LOST (sets converted_at timestamp)
    """
    payload = {}
    if status:              payload["status"] = status
    if lead_type:           payload["lead_type"] = lead_type
    if quality_score:       payload["quality_score"] = quality_score
    if client_response:     payload["client_response"] = client_response
    if notes:               payload["notes"] = notes
    if conversion_status:  payload["conversion_status"] = conversion_status
    if pitch_sent:          payload["pitch_sent"] = pitch_sent

    if not payload:
        raise CRMError("update_lead called with no fields to update")

    result = _api_request("PATCH", f"/leads/{lead_id}", body=payload)
    log(f"Updated lead {lead_id}: {', '.join(payload.keys())}")
    return result


def add_lead_note(lead_id: str, note: str) -> dict:
    """Append a note to a lead's notes field (adds timestamp prefix)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return update_lead(lead_id, notes=f"[{ts}] {note}")


def mark_lead_sent(lead_id: str, pitch_sent: str = None) -> dict:
    """Mark a lead as SENT (pitch delivered to journalist/prospect)."""
    return update_lead(lead_id, status="SENT", pitch_sent=pitch_sent)


def mark_lead_converted(lead_id: str, client_response: str = None) -> dict:
    """Mark a lead as CONVERTED."""
    return update_lead(
        lead_id,
        status="CONVERTED",
        conversion_status="CONVERTED",
        client_response=client_response or "Lead converted via RankBuilder",
    )


def mark_lead_lost(lead_id: str, reason: str = None) -> dict:
    """Mark a lead as LOST."""
    return update_lead(
        lead_id,
        status="LOST",
        conversion_status="LOST",
        client_response=reason or "Lead marked as lost",
    )


def get_lead(lead_id: str) -> dict:
    """Fetch a single lead by ID."""
    return _api_request("GET", f"/leads/{lead_id}")


def get_leads(client_id: str = None, status: str = None, source: str = None,
               limit: int = 50, offset: int = 0) -> dict:
    """
    Fetch leads with optional filters.
    Returns {"leads": [...], "total": N}.
    """
    client_id = client_id or CRM_CLIENT_ID
    params = [f"client_id={urllib.parse.quote(client_id)}"]
    if status:  params.append(f"status={urllib.parse.quote(status)}")
    if source:  params.append(f"source={urllib.parse.quote(source)}")
    params.append(f"limit={limit}")
    params.append(f"offset={offset}")
    qs = "&".join(params)
    return _api_request("GET", f"/leads?{qs}")


# ── Health check ──────────────────────────────────────────────────────────────

def ping() -> bool:
    """Return True if the CRM backend is reachable."""
    try:
        _api_request("GET", "/health", authenticated=False)
        return True
    except Exception:
        return False


def ensure_crm_available(retries: int = 3) -> bool:
    """Wait up to `retries` seconds for CRM to come online."""
    import time
    for i in range(retries):
        if ping():
            return True
        log(f"CRM not reachable, retry {i+1}/{retries}...")
        time.sleep(1)
    log_error(f"CRM unreachable after {retries} attempts — leads will not be saved")
    return False
