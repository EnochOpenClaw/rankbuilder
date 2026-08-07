#!/usr/bin/env python3
"""
RankBuilder CRM — Facebook Lead Ads Poller (fallback)
=====================================================
Polls the Facebook Lead Ads Retrieval API for new leads and pushes
them into the CRM. Used as a fallback when webhooks aren't configured,
or as a safety net alongside the webhook.

Usage
-----
  python3 facebook_lead_poller.py [--page-id PAGE_ID] [--dry-run]

Config (env vars)
-----------------
  FB_PAGE_ID          — Facebook Page ID (required)
  FB_PAGE_ACCESS_TOKEN — Page access token with leads_retrieval permission
  FB_CRM_API_KEY      — CRM client API key (X-API-Key)
  FB_CRM_API_URL      — CRM public endpoint base (default https://dashboard.fortressblinds.co.za/api)
  FB_CRM_SOURCE_DETAIL — source_detail label (default "Facebook Lead Ad")
  FB_STATE_FILE       — path to state file tracking processed lead IDs
                        (default: ./facebook_lead_state.json)

Cron
----
  */15 * * * *  cd /root/rankbuilder && venv/bin/python3 scripts/facebook_lead_poller.py >> scripts/logs/facebook_poller.log 2>&1
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("fb_poller")

# ── Config ─────────────────────────────────────────────────────────────────────
PAGE_ID = os.environ.get("FB_PAGE_ID", "")
PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
CRM_API_KEY = os.environ.get("FB_CRM_API_KEY", "")
CRM_API_URL = os.environ.get(
    "FB_CRM_API_URL", "https://dashboard.fortressblinds.co.za/api"
).rstrip("/")
SOURCE_DETAIL = os.environ.get("FB_CRM_SOURCE_DETAIL", "Facebook Lead Ad")
STATE_FILE = Path(os.environ.get("FB_STATE_FILE", "./facebook_lead_state.json"))

GRAPH_API = "https://graph.facebook.com/v19.0"


def load_state() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("processed", []))
        except Exception:
            pass
    return set()


def save_state(processed: set):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"processed": sorted(processed)}))


def fetch_leads(page_id: str, token: str, limit: int = 25) -> list:
    """Fetch recent leads from the Lead Ads Retrieval API."""
    url = (
        f"{GRAPH_API}/{page_id}/leads"
        f"?access_token={urllib.parse.quote(token)}"
        f"&limit={limit}"
        f"&fields=id,created_time,ad_id,ad_name,adset_id,adset_name,"
        f"campaign_id,campaign_name,form_id,page_id,field_data"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Graph API leads fetch failed (HTTP {e.code}): {body[:300]}")
        return []
    except Exception as e:
        log.error(f"Graph API leads fetch error: {e}")
        return []
    return data.get("data", [])


def normalize_lead(raw: dict) -> dict:
    """Normalize a raw Graph API lead into CRM fields."""
    fields = {}
    for fd in raw.get("field_data", []):
        name = fd.get("name", "")
        values = fd.get("values", [])
        if values:
            fields[name] = values[0]

    def _pick(*names):
        for n in names:
            if fields.get(n):
                return fields[n]
        return None

    full_name = _pick("full_name", "name")
    first = _pick("first_name", "fname")
    last = _pick("last_name", "lname")
    if not full_name and first:
        full_name = f"{first} {last or ''}".strip()

    return {
        "contact_name": full_name,
        "contact_email": _pick("email", "email_address"),
        "contact_phone": _pick("phone_number", "phone", "mobile"),
        "company_name": _pick("company_name", "work_company"),
        "location": _pick("city", "city_name", "state", "zip_code"),
        "product_interest": _pick("product_interest", "product", "service"),
        "message": _pick("message", "comments", "notes"),
        "utm_campaign": raw.get("campaign_name") or _pick("campaign_name"),
        "ad_name": raw.get("ad_name"),
        "adset_name": raw.get("adset_name"),
        "form_id": raw.get("form_id"),
        "leadgen_id": raw.get("id"),
        "created_time": raw.get("created_time"),
    }


def push_to_crm(lead: dict) -> dict:
    """Push a normalized lead to the CRM public endpoint."""
    payload = {
        "contact_name": lead.get("contact_name"),
        "contact_email": lead.get("contact_email"),
        "contact_phone": lead.get("contact_phone"),
        "company_name": lead.get("company_name"),
        "product_interest": lead.get("product_interest"),
        "location": lead.get("location"),
        "message": lead.get("message"),
        "utm_source": "facebook",
        "utm_medium": "lead_ad",
        "utm_campaign": lead.get("utm_campaign"),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{CRM_API_URL}/leads/public",
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": CRM_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info(f"CRM accepted FB lead {lead.get('leadgen_id')}: {result}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"CRM rejected FB lead (HTTP {e.code}): {body[:300]}")
        return {"success": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        log.error(f"CRM push failed: {e}")
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Facebook Lead Ads poller")
    parser.add_argument("--page-id", default=PAGE_ID, help="Facebook Page ID")
    parser.add_argument("--dry-run", action="store_true", help="Don't push to CRM, just report")
    args = parser.parse_args()

    page_id = args.page_id or PAGE_ID
    if not page_id:
        log.error("No FB_PAGE_ID provided (use --page-id or env)")
        sys.exit(1)
    if not PAGE_ACCESS_TOKEN:
        log.error("No FB_PAGE_ACCESS_TOKEN provided")
        sys.exit(1)
    if not CRM_API_KEY:
        log.error("No FB_CRM_API_KEY provided")
        sys.exit(1)

    processed = load_state()
    leads = fetch_leads(page_id, PAGE_ACCESS_TOKEN)

    new_count = 0
    for raw in leads:
        lead_id = raw.get("id")
        if not lead_id or lead_id in processed:
            continue

        lead = normalize_lead(raw)
        log.info(f"New FB lead {lead_id}: {lead.get('contact_name')} <{lead.get('contact_email')}>")

        if not args.dry_run:
            result = push_to_crm(lead)
            if result.get("success"):
                processed.add(lead_id)
                new_count += 1
            else:
                log.error(f"Failed to push lead {lead_id}: {result}")
        else:
            processed.add(lead_id)
            new_count += 1

    save_state(processed)
    log.info(f"Poller done: {new_count} new lead(s) processed, {len(processed)} total tracked")


if __name__ == "__main__":
    main()
