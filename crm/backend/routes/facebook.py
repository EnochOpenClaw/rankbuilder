"""
RankBuilder CRM — Facebook Lead Ads Webhook Receiver
====================================================
Receives Meta (Facebook/Instagram) Lead Ads webhook deliveries and
pushes them into the CRM as FACEBOOK-source leads.

Endpoints
---------
GET  /api/facebook/webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
     Meta's webhook verification handshake. Must return hub.challenge verbatim.

POST /api/facebook/webhook
     Meta's lead delivery. Body is the standard Graph API webhook envelope:
       { "object": "page", "entry": [ { "id": <page_id>, "time": ...,
           "changes": [ { "field": "leadgen", "value": { "leadgen_id": ...,
                          "page_id": ..., "form_id": ... } } ] } ] }

Config (env vars, set in systemd service / .env)
------------------------------------------------
FB_VERIFY_TOKEN   — your chosen verify token (set in Meta App Dashboard webhook config)
FB_PAGE_ACCESS_TOKEN — Page access token with leads_retrieval permission
                      (used to fetch full lead details via Graph API)
FB_CRM_API_KEY    — the CRM client API key (X-API-Key) for the public lead endpoint
FB_CRM_API_URL    — base URL of the CRM public endpoint (default: https://dashboard.fortressblinds.co.za/api)
FB_CRM_SOURCE_DETAIL — source_detail label (default: "Facebook Lead Ad")
"""

import json
import logging
import os
import urllib.request
import urllib.parse
import urllib.error

from fastapi import APIRouter, Request, Response, HTTPException, Query

log = logging.getLogger("crm.facebook")

router = APIRouter()

# ── Config ─────────────────────────────────────────────────────────────────────
VERIFY_TOKEN = os.environ.get("FB_VERIFY_TOKEN", "")
PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
CRM_API_KEY = os.environ.get("FB_CRM_API_KEY", "")
CRM_API_URL = os.environ.get(
    "FB_CRM_API_URL", "https://dashboard.fortressblinds.co.za/api"
).rstrip("/")
SOURCE_DETAIL = os.environ.get("FB_CRM_SOURCE_DETAIL", "Facebook Lead Ad")

GRAPH_API = "https://graph.facebook.com/v19.0"


def _crm_public_url() -> str:
    return f"{CRM_API_URL}/leads/public"


def _push_to_crm(lead_data: dict) -> dict:
    """
    Push a normalized lead to the CRM public endpoint.
    Returns the CRM response dict.
    """
    payload = {
        "contact_name": lead_data.get("contact_name"),
        "contact_email": lead_data.get("contact_email"),
        "contact_phone": lead_data.get("contact_phone"),
        "company_name": lead_data.get("company_name"),
        "product_interest": lead_data.get("product_interest"),
        "location": lead_data.get("location"),
        "message": lead_data.get("message"),
        "utm_source": lead_data.get("utm_source") or "facebook",
        "utm_medium": lead_data.get("utm_medium") or "lead_ad",
        "utm_campaign": lead_data.get("utm_campaign"),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _crm_public_url(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": CRM_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info(f"CRM accepted FB lead: {result}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"CRM rejected FB lead (HTTP {e.code}): {body[:300]}")
        return {"success": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        log.error(f"CRM push failed: {e}")
        return {"success": False, "error": str(e)}


def _fetch_lead_details(leadgen_id: str) -> dict:
    """
    Fetch full lead details from the Graph API Lead Ads Retrieval endpoint.
    Returns a normalized dict of lead fields.
    """
    if not PAGE_ACCESS_TOKEN:
        log.warning("FB_PAGE_ACCESS_TOKEN not set — cannot fetch lead details")
        return {}

    url = (
        f"{GRAPH_API}/{leadgen_id}"
        f"?access_token={urllib.parse.quote(PAGE_ACCESS_TOKEN)}"
        f"&fields=id,created_time,ad_id,ad_name,adset_id,adset_name,"
        f"campaign_id,campaign_name,form_id,page_id,field_data"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Graph API lead fetch failed (HTTP {e.code}): {body[:300]}")
        return {}
    except Exception as e:
        log.error(f"Graph API lead fetch error: {e}")
        return {}

    # Normalize field_data (list of {name, values}) into a flat dict
    fields = {}
    for fd in data.get("field_data", []):
        name = fd.get("name", "")
        values = fd.get("values", [])
        if values:
            fields[name] = values[0]

    # Map common Facebook lead fields → CRM fields
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
        "utm_campaign": data.get("campaign_name") or _pick("campaign_name"),
        "ad_name": data.get("ad_name"),
        "adset_name": data.get("adset_name"),
        "form_id": data.get("form_id"),
        "leadgen_id": data.get("id"),
        "created_time": data.get("created_time"),
    }


@router.get("/facebook/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification handshake.
    Meta calls this with ?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<challenge>
    We must return hub.challenge verbatim if the verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        log.info("Facebook webhook verified ✅")
        return Response(content=hub_challenge, media_type="text/plain")
    log.warning(f"Facebook webhook verification failed (mode={hub_mode})")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/facebook/webhook")
async def receive_webhook(request: Request):
    """
    Receive Facebook lead delivery.
    Body: { "object": "page", "entry": [ { "id": ..., "changes": [...] } ] }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if body.get("object") != "page":
        # Not a page webhook — acknowledge to stop retries
        return {"status": "ignored"}

    created = 0
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value", {})
            leadgen_id = value.get("leadgen_id")
            if not leadgen_id:
                continue

            # Fetch full lead details from Graph API
            lead = _fetch_lead_details(leadgen_id)
            if not lead:
                log.warning(f"No lead details for leadgen_id={leadgen_id}")
                continue

            # Push to CRM
            result = _push_to_crm(lead)
            if result.get("success"):
                created += 1
            else:
                log.error(f"Failed to push FB lead {leadgen_id}: {result}")

    log.info(f"Facebook webhook processed: {created} lead(s) created")
    # Always return 200 to Meta to stop retries
    return {"status": "ok", "created": created}
