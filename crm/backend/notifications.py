"""
RankBuilder CRM — Email Notifications via Brevo
Sends alerts to clients when leads arrive or status changes.
"""

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional
import os

log = logging.getLogger("crm.notifications")

# ── Brevo / SMTP config ────────────────────────────────────────────────────────
# These env vars are picked up from the host environment by uvicorn,
# or set explicitly in the systemd service environment.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
if not BREVO_API_KEY:
    import logging
    logging.getLogger("crm.notifications").warning(
        "BREVO_API_KEY not set — email notifications disabled"
    )
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "craig@fortressblinds.co.za")
SENDER_NAME = "Craig Pauls"

# ── Route-based senders ────────────────────────────────────────────────────────
# Sales/quote leads → notify Tiaan from sales@
# Backlink/blog/outreach leads → notify Craig from craig@
SALES_SENDER_EMAIL = os.environ.get("SALES_SENDER_EMAIL", "sales@fortressblinds.co.za")
SALES_SENDER_NAME = "Fortress Blinds Sales"

# Lead sources that are SALES leads (need fast response + Tiaan)
SALES_SOURCES = {"WEBSITE", "CALL_IN", "DIRECT_MAIL", "FACEBOOK", "MANUAL"}
# Lead sources that are BACKLINK/BLOG/OUTREACH (need Craig follow-up)
OUTREACH_SOURCES = {"HARO", "CONNECTIVELY", "GUEST_OUTREACH", "WEB_SEARCH"}


# ── Low-level Brevo send ───────────────────────────────────────────────────────

def _brevo_send(to_email: str, subject: str, html_body: str, to_name: str = "",
                sender_email: str = None, sender_name: str = None) -> dict:
    """Send transactional email via Brevo SMTP API."""
    sender_email = sender_email or SENDER_EMAIL
    sender_name = sender_name or SENDER_NAME
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": to_name}] if to_name else [{"email": to_email}],
        "htmlContent": html_body,
        "sender": {"name": sender_name, "email": sender_email},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BREVO_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json", "api-key": BREVO_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            msg_id = result.get("messageId", "")
            log.info(f"Brevo sent to {to_email}, messageId={msg_id}")
            return {"success": True, "message_id": msg_id}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Brevo HTTP {e.code} sending to {to_email}: {body[:200]}")
        return {"success": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        log.error(f"Brevo error sending to {to_email}: {e}")
        return {"success": False, "error": str(e)}


# ── Per-lead HTML templates ────────────────────────────────────────────────────

def _lead_source_badge(source: str) -> str:
    badges = {
        "HARO": "#0066cc",
        "CONNECTIVELY": "#6a46c8",
        "GUEST_OUTREACH": "#2e7d32",
        "WEB_SEARCH": "#c85a00",
        "MANUAL": "#666666",
    }
    color = badges.get(source.upper(), "#333333")
    return f"<span style='background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:bold;'>{source}</span>"


def _quality_stars(score: int) -> str:
    score = max(1, min(5, score or 3))
    filled = "★" * score
    empty = "☆" * (5 - score)
    return f"<span style='color:#f5a623;font-size:16px;'>{filled}{empty}</span>"


def _lead_detail_html(lead: dict) -> str:
    fields = []
    for label, key in [
        ("Company", "company_name"),
        ("Contact", "contact_name"),
        ("Email", "contact_email"),
        ("Phone", "contact_phone"),
        ("Website", "company_website"),
        ("Source Query", "source_query"),
        ("Quality", None),
        ("Status", "status"),
    ]:
        if key:
            val = (lead.get(key) or "").strip()
            if val:
                fields.append(f"<tr><td style='padding:4px 12px;color:#666;width:120px;'><strong>{label}:</strong></td><td style='padding:4px 0;'>{val}</td></tr>")
        elif label == "Quality":
            score = lead.get("quality_score") or 3
            fields.append(f"<tr><td style='padding:4px 12px;color:#666;width:120px;'><strong>Quality:</strong></td><td style='padding:4px 0;'>{_quality_stars(score)}</td></tr>")

    msg = (lead.get("message_excerpt") or "").strip()
    pitch = (lead.get("pitch_sent") or "").strip()

    html = f"""
<table style='width:100%;border-collapse:collapse;margin-bottom:16px;'>
  <tr><td colspan='2' style='padding:4px 12px;color:#666;'><strong>Source:</strong> {_lead_source_badge(lead.get('source',''))}</td></tr>
  {''.join(fields)}
</table>"""

    if msg:
        snippet = msg[:300] + ("..." if len(msg) > 300 else "")
        html += f"""
<div style='background:#f8f9fa;border-left:4px solid #0066cc;padding:12px;margin-bottom:12px;border-radius:4px;'>
  <p style='margin:0 0 6px;color:#666;font-size:12px;'><strong>Lead context / message:</strong></p>
  <p style='margin:0;font-style:italic;'>{snippet}</p>
</div>"""

    if pitch:
        snippet = pitch[:300] + ("..." if len(pitch) > 300 else "")
        html += f"""
<div style='background:#e8f5e9;border-left:4px solid #2e7d32;padding:12px;border-radius:4px;'>
  <p style='margin:0 0 6px;color:#666;font-size:12px;'><strong>Pitch sent:</strong></p>
  <p style='margin:0;'>{snippet}</p>
</div>"""

    return html


# ── Notification triggers ──────────────────────────────────────────────────────

def notify_new_lead(lead: dict, db=None) -> None:
    """
    Called when a new lead is created in the CRM.
    Routes by source:
      - SALES leads (WEBSITE/CALL_IN/DIRECT_MAIL/FACEBOOK/MANUAL) → Tiaan, from sales@
      - OUTREACH leads (HARO/CONNECTIVELY/GUEST_OUTREACH/WEB_SEARCH) → Craig, from craig@
    """
    client_id = lead.get("client_id")
    if not client_id:
        return

    source = (lead.get("source") or "UNKNOWN").upper()
    is_sales = source in SALES_SOURCES

    # Determine sender + recipients based on route
    if is_sales:
        sender_email = SALES_SENDER_EMAIL
        sender_name = SALES_SENDER_NAME
        recipients = [("tiaan@houseofsupreme.co.za", "Tiaan")]
    else:
        sender_email = SENDER_EMAIL
        sender_name = SENDER_NAME
        recipients = [("craig@fortressblinds.co.za", "Craig")]

    company = lead.get("company_name") or "Unknown company"
    subject = f"🔔 [RankBuilder] New {source} Lead: {company}"
    badge = _lead_source_badge(source)

    html_body = f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>🎯 New Lead Alert</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>

    <div style='margin-bottom:20px;'>{badge}</div>

    <h2 style='margin:0 0 16px;font-size:18px;color:#111;'>{company}</h2>

    {_lead_detail_html(lead)}

    <div style='margin-top:24px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0 0 8px;color:#333;font-size:14px;'><strong>What to do next:</strong></p>
      <p style='margin:0;color:#666;font-size:13px;'>Review this lead in the CRM portal. Update the status to CONTACTED once you've reached out, or mark CONVERTED/LOST when the outcome is known.</p>
    </div>

    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>
      RankBuilder CRM · House of Supreme · Powered by AgenticFlows
    </p>
  </div>
</body>
</html>"""

    for email, name in recipients:
        _brevo_send(email, subject, html_body, to_name=name,
                    sender_email=sender_email, sender_name=sender_name)


def notify_lead_sent(lead: dict, db=None) -> None:
    """
    Called when a lead's pitch is sent to the journalist/editor.
    Notifies client that their expert quote is on its way.
    """
    client_id = lead.get("client_id")
    if not client_id:
        return

    recipients = _get_notification_recipients(client_id, db)
    if not recipients:
        return

    company = lead.get("company_name") or "Unknown"
    source = lead.get("source", "UNKNOWN")
    subject = f"📤 [RankBuilder] Pitch Sent: {company}"
    badge = _lead_source_badge(source)

    pitch = (lead.get("pitch_sent") or "").strip()[:300]

    html_body = f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>📤 Pitch Sent</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>

    <div style='margin-bottom:20px;'>{badge}</div>

    <h2 style='margin:0 0 16px;font-size:18px;color:#111;'>{company}</h2>

    <p style='color:#555;font-size:14px;margin:0 0 16px;'>
      Your expert pitch has been sent to the journalist/editor. You'll be notified when the article is published or when there's a response.
    </p>

    {f"""
    <div style='background:#f8f9fa;border-left:4px solid #2e7d32;padding:12px;border-radius:4px;margin-bottom:16px;'>
      <p style='margin:0 0 6px;color:#666;font-size:12px;'><strong>Pitch preview:</strong></p>
      <p style='margin:0;font-size:13px;'>{pitch}{'...' if len(lead.get('pitch_sent','') or '') > 300 else ''}</p>
    </div>""" if pitch else ""}

    <div style='margin-top:24px;padding:16px;background:#fff8e1;border-radius:8px;'>
      <p style='margin:0;color:#666;font-size:13px;'>The CRM will automatically update the lead status when a response is received or the article is published.</p>
    </div>

    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>
      RankBuilder CRM · House of Supreme · Powered by AgenticFlows
    </p>
  </div>
</body>
</html>"""

    for email, name in recipients:
        _brevo_send(email, subject, html_body, to_name=name)


# ── Notification recipients lookup ────────────────────────────────────────────

def _get_notification_recipients(client_id: str, db) -> list[tuple[str, str]]:
    """
    Look up notification email addresses for a client.
    Returns list of (email, display_name) tuples.
    Falls back to a hardcoded HOS list if DB lookup fails.
    """
    # Fast path: if no db provided, use HOS defaults
    HOS_DEFAULT = [
        ("tiaan@houseofsupreme.co.za", "Tiaan"),
        ("robin@houseofsupreme.co.za", "Robin"),
        ("craigp@ct-designs.co.za", "Craig"),
    ]

    if db is None:
        return HOS_DEFAULT

    try:
        from backend.database import Client, NotificationSetting
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return HOS_DEFAULT

        settings = db.query(NotificationSetting).filter(
            NotificationSetting.client_id == client_id,
            NotificationSetting.enabled == True,
        ).all()

        if not settings:
            return HOS_DEFAULT

        recipients = []
        for s in settings:
            if s.notification_type == "EMAIL" and s.target:
                name = s.name or ""
                recipients.append((s.target, name))
        return recipients if recipients else HOS_DEFAULT

    except Exception as e:
        log.warning(f"Notification lookup failed: {e}, using defaults")
        return HOS_DEFAULT
