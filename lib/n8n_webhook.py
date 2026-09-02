"""
n8n Webhook Helper — sends RankBuilder events to the n8n workflow.

Single import, fire-and-forget. Reconstructed 2026-09-02 from the deployed
.pyc (the .py source had been lost, breaking `from lib.n8n_webhook import
send_event` in haro_monitor.py / haro_approve.py).
"""
import json
import urllib.request
import urllib.error
from datetime import datetime

# RankBuilder event hub webhook (n8n on the VPS). Matches TOOLS.md.
N8N_WEBHOOK_URL = "https://n8n.fortressblinds.co.za/webhook/rankbuilder"


def send_event(
    event: str,
    status: str,
    prospect: dict = None,
    query: dict = None,
    message: str = None,
    source: str = None,
    extra: dict = None,
) -> bool:
    """Fire-and-forget POST of an event to the n8n RankBuilder workflow.

    Returns True if the request was dispatched (a network/HTTP error does not
    raise — this is best-effort event logging and must never crash the caller).
    """
    payload: dict = {
        "event": event,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if prospect is not None:
        payload["prospect"] = prospect
    if query is not None:
        payload["query"] = query
    if message is not None:
        payload["message"] = message
    if source is not None:
        payload["source"] = source
    if extra is not None:
        payload.update(extra)

    try:
        req = urllib.request.Request(
            N8N_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        # Best-effort: never raise out of the monitor.
        return False
