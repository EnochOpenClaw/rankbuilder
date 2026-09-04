"""
RankBuilder CRM — Staged Follow-up Reminder / Escalation
=========================================================
Runs via cron (every 30-60 min) and escalates leads that are going cold.

Escalation ladder (per lead, tracked via Lead.reminder_stage):
  - T+24h  (stage 1): reminder to the ASSIGNED REP (per-lead email)
  - T+48h  (stage 2): second, firmer reminder to the ASSIGNED REP
  - T+72h  (stage 3): escalation to MANAGERS (Robin & Vanessa) — they follow up
                      with the rep so nothing falls through the cracks

A lead is 'due' when it is assigned, not converted/lost, and has had no
follow-up in the stage window. Logging a follow-up resets reminder_stage to 0
(handled in backend/assignment.py log_follow_up).
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# Allow running as a standalone script — resolve the CRM backend package.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CRM_ROOT = os.path.join(_HERE, "..", "crm")
if os.path.isdir(_CRM_ROOT) and _CRM_ROOT not in sys.path:
    sys.path.insert(0, _CRM_ROOT)

# Load .env (repo root) so BREVO_API_KEY etc. are available when run via cron.
def _load_env_file():
    env_path = os.path.join(_HERE, "..", ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

_load_env_file()

from backend.database import SessionLocal, Lead, LeadStatus

log = logging.getLogger("crm.followup")

# ── Config ─────────────────────────────────────────────────────────────────────
STAGE_1_HOURS = int(os.environ.get("FOLLOW_UP_REMINDER_HOURS", "24"))  # rep reminder
STAGE_2_HOURS = int(os.environ.get("FOLLOW_UP_STAGE2_HOURS", "48"))     # rep, firmer
STAGE_3_HOURS = int(os.environ.get("FOLLOW_UP_STAGE3_HOURS", "72"))     # managers
# ── Payment-received quiet window ────────────────────────────────────────────
# Once a lead's payment is RECEIVED (job won, install in progress), suppress the
# follow-up/escalation nudges for this many days. After the window the normal
# ladder can resume if the lead is still open. Default 7 days (1 week).
PAYMENT_QUIET_DAYS = int(os.environ.get("PAYMENT_QUIET_DAYS", "7"))
MANAGER_EMAILS = [
    ("robin@houseofsupreme.co.za", "Robin Bras"),
    ("vanessa@houseofsupreme.co.za", "Vanessa Bras"),
    ("lee-ann@houseofsupreme.co.za", "Lee-Ann Van Zyl"),
]

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "sales@fortressblinds.co.za")
SENDER_NAME = "Fortress Blinds Sales"

# Use the shared Brevo sender from the CRM backend so every notification send is
# also logged per-lead in email_logs (audit trail, does not affect follow-up state).
from backend.notifications import _brevo_send


def _lead_row(lead):
    name = lead.contact_name or lead.company_name or "Lead"
    loc = lead.location or "Unknown area"
    phone = lead.contact_phone or "—"
    last_fu = lead.last_follow_up_at.strftime("%Y-%m-%d %H:%M") if lead.last_follow_up_at else "Never"
    created = lead.created_at.strftime("%Y-%m-%d") if lead.created_at else "—"
    return {
        "id": lead.id,
        "name": name,
        "loc": loc,
        "phone": phone,
        "last_fu": last_fu,
        "created": created,
        "company": lead.company_name or name,
        "assigned_name": lead.assigned_to_name or lead.assigned_to or "rep",
    }


def _template(lead, heading, intro, cta, urgency_color):
    r = _lead_row(lead)
    return f"""
    <!DOCTYPE html><html><body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
    <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
      <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
        <h1 style='margin:0;font-size:20px;color:#333;'>{heading}</h1>
        <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      </div>
      {intro}
      <div style='background:#f5f5f5;border-left:4px solid {urgency_color};padding:14px;border-radius:6px;margin:16px 0;'>
        <p style='margin:0 0 8px;font-size:15px;color:#111;'><strong>{r['company']}</strong> — {r['name']}</p>
        <table style='width:100%;border-collapse:collapse;font-size:13px;color:#444;'>
          <tr><td style='padding:3px 0;width:100px;color:#888;'>Area</td><td>{r['loc']}</td></tr>
          <tr><td style='padding:3px 0;color:#888;'>Phone</td><td>{r['phone']}</td></tr>
          <tr><td style='padding:3px 0;color:#888;'>Created</td><td>{r['created']}</td></tr>
          <tr><td style='padding:3px 0;color:#888;'>Last follow-up</td><td>{r['last_fu']}</td></tr>
        </table>
      </div>
      {cta}
      <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>RankBuilder CRM · House of Supreme · Powered by AgenticFlows</p>
    </div></body></html>
    """


def _stage1_email(lead):
    r = _lead_row(lead)
    intro = f"<p style='color:#555;font-size:14px;'>Hi <strong>{r['assigned_name']}</strong>, this lead was allocated to you and hasn't had an update in <strong>24+ hours</strong>.</p>"
    cta = (
        "<div style='margin-top:16px;padding:14px;background:#eef2ff;border-radius:8px;text-align:center;'>"
        "<p style='margin:0;color:#333;font-size:14px;'><strong>Please log a follow-up</strong> in the CRM portal "
        "(call the client, update the status, or mark CONVERTED/LOST if resolved).</p></div>"
    )
    return _template(lead, "📞 Follow-up Due", intro, cta, "#1e88e5"), \
        f"📞 [RankBuilder] Follow-up Due: {r['company']}"


def _stage2_email(lead):
    r = _lead_row(lead)
    intro = f"<p style='color:#555;font-size:14px;'>Hi <strong>{r['assigned_name']}</strong>, this lead is now <strong>48+ hours</strong> without an update. Please action it today.</p>"
    cta = (
        "<div style='margin-top:16px;padding:14px;background:#fff3e0;border-radius:8px;text-align:center;'>"
        "<p style='margin:0;color:#333;font-size:14px;'><strong>Action required:</strong> log your follow-up in the CRM now. "
        "If the lead is no longer relevant, mark it LOST so it stops pinging.</p></div>"
    )
    return _template(lead, "⚠️ Follow-up Overdue (48h)", intro, cta, "#fb8c00"), \
        f"⚠️ [RankBuilder] Follow-up Overdue: {r['company']}"


def _stage3_email(lead):
    r = _lead_row(lead)
    intro = (
        f"<p style='color:#555;font-size:14px;'>This lead has had <strong>no update in 72+ hours</strong>. "
        f"It was allocated to <strong>{r['assigned_name']}</strong> and is going cold.</p>"
    )
    cta = (
        "<div style='margin-top:16px;padding:14px;background:#fdecea;border-radius:8px;text-align:center;'>"
        "<p style='margin:0;color:#b71c1c;font-size:14px;'><strong>Escalation:</strong> please follow up with the "
        "assigned rep to ensure this lead is actioned or closed.</p></div>"
    )
    return _template(lead, "🚨 Lead Escalation (72h)", intro, cta, "#d32f2f"), \
        f"🚨 [RankBuilder] Lead Escalation: {r['company']}"


def main():
    if not BREVO_API_KEY:
        log.warning("BREVO_API_KEY not set — skipping follow-up reminders")
        return

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        leads = (
            db.query(Lead)
            .filter(
                Lead.assigned_to.isnot(None),
                Lead.status.notin_([LeadStatus.CONVERTED, LeadStatus.LOST]),
                Lead.archived == 0,  # archived deals stop pinging
                Lead.partner_handoff_id.is_(None),  # skip leads handed off to a partner
            )
            .all()
        )

        sent = {"stage1": 0, "stage2": 0, "stage3": 0}
        for lead in leads:
            # ── Payment-received quiet window ──────────────────────────────
            # If payment was received within the last PAYMENT_QUIET_DAYS, the job
            # is in install/production — don't nag the team about follow-up yet.
            if lead.payment_status == "RECEIVED" and lead.payment_received_at:
                pr = lead.payment_received_at
                if pr.tzinfo is None:
                    pr = pr.replace(tzinfo=timezone.utc)
                if (now - pr).total_seconds() < PAYMENT_QUIET_DAYS * 86400:
                    continue  # in quiet window — skip follow-up nudges

            # Reference time: last follow-up if present, else creation
            ref = lead.last_follow_up_at or lead.created_at
            if ref is None:
                continue
            # Make tz-aware for comparison
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            age_hours = (now - ref).total_seconds() / 3600
            stage = lead.reminder_stage or 0

            # Stage 3: escalate to managers
            if stage < 3 and age_hours >= STAGE_3_HOURS:
                html, subj = _stage3_email(lead)
                for m_email, m_name in MANAGER_EMAILS:
                    _brevo_send(m_email, subj, html, to_name=m_name,
                                sender_email=SENDER_EMAIL, sender_name=SENDER_NAME,
                                lead_id=lead.id, notification_type="follow_up")
                lead.reminder_stage = 3
                sent["stage3"] += 1
                db.add(lead)
            # Stage 2: firmer reminder to rep
            elif stage < 2 and age_hours >= STAGE_2_HOURS:
                html, subj = _stage2_email(lead)
                _brevo_send(lead.assigned_to, subj, html, to_name=lead.assigned_to_name or "",
                            sender_email=SENDER_EMAIL, sender_name=SENDER_NAME,
                            lead_id=lead.id, notification_type="follow_up")
                lead.reminder_stage = 2
                sent["stage2"] += 1
                db.add(lead)
            # Stage 1: first reminder to rep
            elif stage < 1 and age_hours >= STAGE_1_HOURS:
                html, subj = _stage1_email(lead)
                _brevo_send(lead.assigned_to, subj, html, to_name=lead.assigned_to_name or "",
                            sender_email=SENDER_EMAIL, sender_name=SENDER_NAME,
                            lead_id=lead.id, notification_type="follow_up")
                lead.reminder_stage = 1
                sent["stage1"] += 1
                db.add(lead)

        db.commit()
        log.info(f"Reminders sent: {sent}")
        if sum(sent.values()) == 0:
            log.info("No leads due for follow-up")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
