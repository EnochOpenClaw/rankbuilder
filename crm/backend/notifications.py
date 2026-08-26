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
from backend.assignment import _contains_keywords, CAPE_TOWN_KEYWORDS
from backend.database import SessionLocal, EmailLog

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

# Lead sources that are SALES leads (need fast response + sales team)
# ROADSIDE (gazebo form fills), PPC and WORD_OF_MOUTH are also sales prospects
# → notify the HOS sales team, not just Craig.
SALES_SOURCES = {"WEBSITE", "CALL_IN", "DIRECT_MAIL", "FACEBOOK", "MANUAL",
                 "ROADSIDE", "PPC", "WORD_OF_MOUTH"}
# Lead sources that are BACKLINK/BLOG/OUTREACH (need Craig follow-up)
OUTREACH_SOURCES = {"HARO", "CONNECTIVELY", "GUEST_OUTREACH", "WEB_SEARCH"}

# ── New-lead notification groups (House of Supreme) ───────────────────
# Management — Robin, Vanessa, Lee-Ann: notified on EVERY new sales lead
# Cape Town  — Richard, Irene: notified only for Cape Town region leads
# Tiaan      — standalone: own 'allocated to you' email, no broadcast
# Freedom    — AGENT: removed from broadcast
MGMT_EMAILS = [
    ("robin@houseofsupreme.co.za", "Robin Bras"),
    ("vanessa@houseofsupreme.co.za", "Vanessa Bras"),
    ("lee-ann@houseofsupreme.co.za", "Lee-Ann Van Zyl"),
]
CAPE_TOWN_GROUP = [
    ("richard@houseofsupreme.co.za", "Richard Turner"),
    ("irene@houseofsupreme.co.za", "Irene Basson"),
]

def _is_cape_town(location) -> bool:
    return bool(location) and _contains_keywords(str(location), CAPE_TOWN_KEYWORDS)



# ── Low-level Brevo send ───────────────────────────────────────────────────────

def _log_email(lead_id: str, to_email: str, subject: str, direction: str = "OUTBOUND",
               notification_type: str = None, status: str = "SENT", message_id: str = "",
               from_email: str = "", body: str = ""):
    """Persist an email record against a lead WITHOUT touching its follow-up state.

    Writes to email_logs only — never to lead_activities/lead_history/last_follow_up_at,
    so "needs follow-up" status is unaffected.
    """
    if not lead_id:
        return
    try:
        session = SessionLocal()
        try:
            session.add(EmailLog(
                lead_id=lead_id,
                direction=direction,
                notification_type=notification_type or "manual",
                status=status,
                message_id=message_id,
                subject=subject,
                body=body,
                from_email=from_email,
                to_email=to_email,
                created_by="system",
            ))
            session.commit()
        finally:
            session.close()
    except Exception as e:
        log.error(f"Failed to persist email log for lead {lead_id}: {e}")


def _brevo_send(to_email: str, subject: str, html_body: str, to_name: str = "",
                sender_email: str = None, sender_name: str = None,
                lead_id: str = None, notification_type: str = None) -> dict:
    """Send transactional email via Brevo SMTP API.

    If lead_id is provided, the send (success or failure) is logged against the
    lead in email_logs as an audit trail — does NOT affect follow-up status.
    """
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
            _log_email(lead_id, to_email, subject, notification_type=notification_type,
                       status="SENT", message_id=msg_id, from_email=sender_email, body=html_body)
            return {"success": True, "message_id": msg_id}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Brevo HTTP {e.code} sending to {to_email}: {body[:200]}")
        _log_email(lead_id, to_email, subject, notification_type=notification_type,
                   status="FAILED", message_id="", from_email=sender_email, body=body[:500])
        return {"success": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        log.error(f"Brevo error sending to {to_email}: {e}")
        _log_email(lead_id, to_email, subject, notification_type=notification_type,
                   status="FAILED", message_id="", from_email=sender_email, body=str(e)[:500])
        return {"success": False, "error": str(e)}


# ── Per-lead HTML templates ────────────────────────────────────────────────────

def _lead_source_badge(source: str) -> str:
    badges = {
        "HARO": "#0066cc",
        "CONNECTIVELY": "#6a46c8",
        "GUEST_OUTREACH": "#2e7d32",
        "WEB_SEARCH": "#c85a00",
        "MANUAL": "#666666",
        "WEBSITE": "#1677ff",
        "FACEBOOK": "#1877f2",
        "CALL_IN": "#52c41a",
        "DIRECT_MAIL": "#fa8c16",
        "ROADSIDE": "#eb2f96",
        "PPC": "#722ed1",
        "WORD_OF_MOUTH": "#13c2c2",
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
    Routes by assigned rep (region-based):
      - Lead assigned to a rep → notify that rep directly
      - Fallback: SALES sources → Tiaan; OUTREACH sources → Craig
    """
    client_id = lead.get("client_id")
    if not client_id:
        return

    source = (lead.get("source") or "UNKNOWN").upper()
    is_sales = source in SALES_SOURCES

    # Determine recipients:
    #   - Sales leads → notify the full Sales Team group (all 4 HOS reps)
    #   - Outreach leads → notify Craig
    #   - If a specific rep is assigned, still notify the team but highlight the rep
    assigned_to = lead.get("assigned_to")
    assigned_name = lead.get("assigned_to_name") or "Assigned Rep"
    if is_sales:
        sender_email = SALES_SENDER_EMAIL
        sender_name = SALES_SENDER_NAME
        # Group routing:
        #   - Management always
        #   - Cape Town group only for Cape Town region leads
        #   - Tiaan gets his own personal allocation email (no broadcast here)
        #   - Freedom excluded (AGENT)
        recipients = list(MGMT_EMAILS)
        if _is_cape_town(lead.get("location")):
            recipients += CAPE_TOWN_GROUP
        seen = set()
        recipients = [r for r in recipients if not (r[0] in seen or seen.add(r[0]))]
        if not recipients:
            recipients = list(MGMT_EMAILS)
    else:
        sender_email = SENDER_EMAIL
        sender_name = SENDER_NAME
        recipients = [("craig@fortressblinds.co.za", "Craig")]

    company = lead.get("company_name") or "Unknown company"
    subject = f"🔔 [RankBuilder] New {source} Lead: {company}"
    badge = _lead_source_badge(source)

    # Assigned rep highlight
    assigned_block = ""
    if assigned_to:
        assigned_block = f"""
    <div style='margin-bottom:20px;padding:12px;background:#f0f4ff;border:1px solid #dbe4ff;border-radius:8px;'>
      <p style='margin:0;color:#333;font-size:14px;'><strong>Assigned to:</strong> {assigned_name} ({assigned_to})</p>
      <p style='margin:6px 0 0;color:#888;font-size:12px;'>This lead has been auto-routed to you based on the region.</p>
    </div>"""

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
    {assigned_block}

    <h2 style='margin:0 0 16px;font-size:18px;color:#111;'>{company}</h2>

    {_lead_detail_html(lead)}

    <div style='margin-top:24px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0 0 8px;color:#333;font-size:14px;'><strong>What to do next:</strong></p>
      <p style='margin:0;color:#666;font-size:13px;'>Log your follow-up in the CRM portal (assigning it as CONTACTED) so your activity is tracked. Update to CONVERTED/LOST when the outcome is known.</p>
    </div>

    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>
      RankBuilder CRM · House of Supreme · Powered by AgenticFlows
    </p>
  </div>
</body>
</html>"""

    for email, name in recipients:
        _brevo_send(email, subject, html_body, to_name=name,
                    sender_email=sender_email, sender_name=sender_name,
                    lead_id=lead.get("id"), notification_type="new_lead")


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
        _brevo_send(email, subject, html_body, to_name=name,
                    lead_id=lead.get("id"), notification_type="lead_sent")


# ── Notification recipients lookup ────────────────────────────────────────────

def _get_notification_recipients(client_id: str, db) -> list[tuple[str, str]]:
    """
    Look up notification email addresses for a client.
    Returns list of (email, display_name) tuples.
    Falls back to a hardcoded HOS list if DB lookup fails.
    """
    # Fast path: if no db provided, use HOS defaults
    # House of Supreme Sales Team — all 4 notified on new leads
    HOS_DEFAULT = [
        ("lee-ann@houseofsupreme.co.za", "Lee-Ann Van Zyl"),
        ("robin@houseofsupreme.co.za", "Robin Bras"),
        ("tiaan@houseofsupreme.co.za", "Tiaan van der Walt"),
        ("vanessa@houseofsupreme.co.za", "Vanessa Bras"),
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
def notify_lead_allocated(lead: dict, rep_email: str, rep_name: str,
                          allocated_by: str = "system", db=None) -> None:
    """
    Send a dedicated 'Lead Allocated to You' email to the assigned sales rep.

    Fired whenever a lead is assigned to a rep — whether auto-routed on creation
    or manually allocated by a manager via the assign endpoint. Gives the rep a
    clear, personal notification that this lead is theirs and what to do next.
    """
    if not lead or not rep_email:
        return

    client_id = lead.get("client_id")
    company = lead.get("company_name") or "Unknown company"
    contact = lead.get("contact_name") or "—"
    phone = lead.get("contact_phone") or "—"
    location = lead.get("location") or "—"
    source = (lead.get("source") or "UNKNOWN").upper()
    source_detail = lead.get("source_detail") or ""

    # Use sales sender for sales leads, default otherwise
    if source in SALES_SOURCES:
        sender_email = SALES_SENDER_EMAIL
        sender_name = SALES_SENDER_NAME
    else:
        sender_email = SENDER_EMAIL
        sender_name = SENDER_NAME

    by = allocated_by if allocated_by and allocated_by != "system" else "the system (region auto-routing)"
    subject = f"📋 [RankBuilder] Lead Allocated to You: {company}"

    html_body = f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>📋 Lead Allocated to You</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>

    <p style='color:#333;font-size:14px;'>Hi <strong>{rep_name}</strong>,</p>
    <p style='color:#555;font-size:14px;'>A new lead has been <strong>allocated to you</strong> by {by}:</p>

    <div style='background:#f0f4ff;border:1px solid #dbe4ff;border-radius:8px;padding:16px;margin:16px 0;'>
      <h2 style='margin:0 0 12px;font-size:18px;color:#111;'>{company}</h2>
      <table style='width:100%;border-collapse:collapse;font-size:14px;color:#444;'>
        <tr><td style='padding:4px 0;width:110px;color:#888;'>Contact</td><td>{contact}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Phone</td><td>{phone}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Area</td><td>{location}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Source</td><td>{source}{' · ' + source_detail if source_detail else ''}</td></tr>
      </table>
    </div>

    <div style='margin-top:20px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0 0 8px;color:#333;font-size:14px;'><strong>Next step:</strong></p>
      <p style='margin:0;color:#666;font-size:13px;'>Contact the lead and log your follow-up in the CRM portal so your activity is tracked. Update the lead to CONTACTED / CONVERTED / LOST when the outcome is known.</p>
    </div>

    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>
      RankBuilder CRM · House of Supreme · Powered by AgenticFlows
    </p>
  </div>
</body>
</html>"""

    _brevo_send(rep_email, subject, html_body, to_name=rep_name,
                sender_email=sender_email, sender_name=sender_name,
                lead_id=lead.get("id"), notification_type="lead_allocated")
    log.info(f"Allocated notification sent to {rep_email} for lead {company} ({lead.get('id')})")


def notify_hot_lead(lead: dict, db=None) -> None:
    """
    Send an urgent HOT-lead alert when a lead scores >= 70 (high intent).
    Routes to the assigned rep + the client notification group, with a
    distinct 'act fast' tone so hot leads aren't lost in the inbox.
    """
    client_id = lead.get("client_id")
    if not client_id:
        return

    source = (lead.get("source") or "UNKNOWN").upper()
    score = lead.get("quality_score") or 0
    company = lead.get("company_name") or "Unknown company"
    contact = lead.get("contact_name") or "—"
    phone = lead.get("contact_phone") or "—"
    location = lead.get("location") or "—"
    source_detail = lead.get("source_detail") or ""

    # Sales sources use the sales sender; outreach uses the default
    if source in SALES_SOURCES:
        sender_email = SALES_SENDER_EMAIL
        sender_name = SALES_SENDER_NAME
    else:
        sender_email = SENDER_EMAIL
        sender_name = SENDER_NAME

    # Recipients: assigned rep (primary) + the client's notification group
    recipients = set()
    if lead.get("assigned_to"):
        recipients.add((lead["assigned_to"], lead.get("assigned_to_name") or "Rep"))
    for email, name in _get_notification_recipients(client_id, db) or []:
        recipients.add((email, name))

    subject = f"🔥 [RankBuilder] HOT LEAD ({score}/100): {company}"
    badge = _lead_source_badge(source)

    html_body = f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fff1f0;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 12px rgba(245,34,45,0.15);border:2px solid #f5222d;'>
    <div style='background:#f5222d;border-radius:8px;padding:12px 16px;margin-bottom:16px;text-align:center;'>
      <h1 style='margin:0;font-size:22px;color:white;'>🔥 HOT LEAD — Act Fast</h1>
      <p style='margin:6px 0 0;color:#ffd6d6;font-size:13px;'>Auto-scored {score}/100 · High intent</p>
    </div>

    {badge}

    <h2 style='margin:16px 0;font-size:20px;color:#111;'>{company}</h2>
    <table style='width:100%;border-collapse:collapse;font-size:14px;color:#444;'>
      <tr><td style='padding:4px 0;width:110px;color:#888;'>Contact</td><td>{contact}</td></tr>
      <tr><td style='padding:4px 0;color:#888;'>Phone</td><td><a href='tel:{phone}'>{phone}</a></td></tr>
      <tr><td style='padding:4px 0;color:#888;'>Area</td><td>{location}</td></tr>
      <tr><td style='padding:4px 0;color:#888;'>Source</td><td>{source}{' · ' + source_detail if source_detail else ''}</td></tr>
      <tr><td style='padding:4px 0;color:#888;'>Assigned</td><td>{lead.get('assigned_to_name') or '—'}</td></tr>
    </table>

    <div style='margin-top:20px;padding:16px;background:#fff7e6;border-radius:8px;text-align:center;'>
      <p style='margin:0 0 8px;color:#ad4e00;font-size:14px;'><strong>Priority action:</strong></p>
      <p style='margin:0;color:#873800;font-size:13px;'>Contact this lead ASAP — high-intent leads convert fastest when reached first. Log your follow-up in the CRM.</p>
    </div>

    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>
      RankBuilder CRM · Powered by AgenticFlows
    </p>
  </div>
</body>
</html>"""

    for email, name in recipients:
        _brevo_send(email, subject, html_body, to_name=name,
                    sender_email=sender_email, sender_name=sender_name,
                    lead_id=lead.get("id"), notification_type="hot_lead")
    log.info(f"Hot-lead alert sent for {company} ({lead.get('id')}) score={score}")
