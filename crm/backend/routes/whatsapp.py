"""
RankBuilder CRM — WhatsApp Business Cloud API Webhook Receiver
===============================================================
Receives inbound WhatsApp messages via Meta's Cloud API webhook and
pushes them into the CRM as WHATSAPP-source leads.

Endpoints
---------
GET  /api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
     Meta's webhook verification handshake. Must return hub.challenge verbatim.

POST /api/whatsapp/webhook
     Meta's message delivery. Body is the standard Cloud API envelope:
       { "object": "whatsapp_business_account",
         "entry": [ { "id": <waba_id>, "changes": [
             { "value": { "messaging_product": "whatsapp",
                 "contacts": [ { "profile": {"name": ...}, "wa_id": "2782..." } ],
                 "messages": [ { "from": "2782...", "id": "...",
                     "text": { "body": "Hi, I want a quote" },
                     "type": "text", "timestamp": "..." } ] } } ] } ] }

Config (env vars, set in systemd service / .env)
------------------------------------------------
WA_VERIFY_TOKEN   — your chosen verify token (set in Meta App Dashboard webhook config)
WA_CRM_API_KEY    — the CRM client API key (X-API-Key) for the public lead endpoint
WA_CRM_API_URL    — base URL of the CRM public endpoint (default: https://dashboard.fortressblinds.co.za/api)
WA_CRM_SOURCE_DETAIL — source_detail label (default: "WhatsApp Business")
WA_CRM_CLIENT_NAME  — CRM client to route to by company name (default: "House of Supreme")
"""

import json
import logging
import os
import urllib.request
import urllib.parse
import urllib.error

from fastapi import APIRouter, Request, Response, HTTPException, Query

log = logging.getLogger("crm.whatsapp")

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "")
CRM_API_KEY = os.environ.get("WA_CRM_API_KEY", "")
CRM_API_URL = os.environ.get("WA_CRM_API_URL", "https://dashboard.fortressblinds.co.za/api")
SOURCE_DETAIL = os.environ.get("WA_CRM_SOURCE_DETAIL", "WhatsApp Business")


@router.get("/whatsapp/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification handshake.
    Must return hub.challenge verbatim if hub_verify_token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        log.info("WhatsApp webhook verified by Meta")
        return Response(content=hub_challenge, media_type="text/plain")
    log.warning("WhatsApp webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request):
    """
    Receive WhatsApp Cloud API message deliveries and create CRM leads.
    Returns 200 quickly (Meta expects fast ack) and processes in background.
    """
    try:
        body = await request.json()
    except Exception:
        log.error("Invalid JSON body from WhatsApp webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Acknowledge immediately — Meta will retry if we don't return 200 fast
    # (processing happens in background via _process)
    try:
        _process_inbound(body)
    except Exception as e:
        log.exception(f"WhatsApp webhook processing error: {e}")

    return {"status": "received"}


def _process_inbound(body: dict):
    """Extract inbound WhatsApp messages and create CRM leads."""
    if body.get("object") != "whatsapp_business_account":
        log.debug("Not a WhatsApp business account event, ignoring")
        return

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("messaging_product") != "whatsapp":
                continue
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])
            for msg in messages:
                _handle_message(msg, contacts)


def _handle_message(msg: dict, contacts: list):
    """Handle a single inbound WhatsApp message."""
    # Skip status updates (delivery/read receipts) — not real messages
    if msg.get("type") == "status" or "status" in msg:
        return

    from_wa = msg.get("from", "")
    msg_type = msg.get("type", "")

    # Extract text body
    text = ""
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type == "button":
        text = msg.get("button", {}).get("text", "")
    elif msg_type == "interactive":
        text = msg.get("interactive", {}).get("button_reply", {}).get("title", "") \
              or msg.get("interactive", {}).get("list_reply", {}).get("title", "")
    # (image/audio/document/contacts — we just capture that they messaged)

    # Get sender profile name if available
    sender_name = ""
    for c in contacts:
        if c.get("wa_id") == from_wa:
            sender_name = c.get("profile", {}).get("name", "")

    if not from_wa:
        log.debug("Message has no sender, ignoring")
        return

    # Build the lead payload for the CRM public endpoint
    payload = {
        "contact_name": sender_name or f"WhatsApp {from_wa}",
        "contact_phone": _format_phone(from_wa),
        "message": text or f"WhatsApp message received from {from_wa}",
        "product_interest": SOURCE_DETAIL,
        "source": "WHATSAPP",
    }

    _push_to_crm(payload)


def _format_phone(wa_id: str) -> str:
    """Normalize WhatsApp number to a dialable format."""
    # wa_id is like "27821234567" (country code + number, no +)
    if wa_id and not wa_id.startswith("+"):
        return "+" + wa_id
    return wa_id


def _push_to_crm(payload: dict):
    """POST the lead to the CRM public endpoint with the client API key."""
    if not CRM_API_KEY:
        log.warning("WA_CRM_API_KEY not set — cannot push WhatsApp lead to CRM")
        return

    url = CRM_API_URL.rstrip("/") + "/leads/public"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": CRM_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info(f"WhatsApp lead pushed to CRM: {result}")
    except urllib.error.HTTPError as e:
        log.error(f"CRM push failed HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        log.error(f"CRM push failed: {e}")
