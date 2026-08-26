"""
RankBuilder CRM — Scheduled Lead Reminders
==========================================
Runs via cron (every few minutes) and fires user-scheduled reminders.

When a user schedules a reminder on a lead (via the lead drawer), this script
checks for PENDING reminders whose remind_at time has arrived, sends an email
notification to the assigned rep (or the person who scheduled it), and marks
the reminder SENT.
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_CRM_ROOT = os.path.join(_HERE, "..", "crm")
if os.path.isdir(_CRM_ROOT) and _CRM_ROOT not in sys.path:
    sys.path.insert(0, _CRM_ROOT)


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

from backend.database import SessionLocal, Lead, LeadReminder

log = logging.getLogger("crm.reminders")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "ai@fortressblinds.co.za")
SENDER_NAME = "RankBuilder CRM"

# Use the shared Brevo sender from the CRM backend so every reminder send is also
# logged per-lead in email_logs (audit trail, does not affect follow-up state).
from backend.notifications import _brevo_send


def _template(lead, note, remind_at):
    company = lead.company_name or "Unknown company"
    contact = lead.contact_name or "—"
    phone = lead.contact_phone or "—"
    location = lead.location or "—"
    note_html = f'<p style="margin:12px 0 0;color:#555;font-size:14px;"><strong>Note:</strong> {note}</p>' if note else ""
    return f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>⏰ Scheduled Reminder</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
    <p style='color:#333;font-size:14px;'>This is your scheduled reminder for the lead below:</p>
    <div style='background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:16px;margin:16px 0;'>
      <h2 style='margin:0 0 12px;font-size:18px;color:#111;'>{company}</h2>
      <table style='width:100%;border-collapse:collapse;font-size:14px;color:#444;'>
        <tr><td style='padding:4px 0;width:110px;color:#888;'>Contact</td><td>{contact}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Phone</td><td>{phone}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Area</td><td>{location}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Scheduled for</td><td>{remind_at}</td></tr>
      </table>
      {note_html}
    </div>
    <div style='margin-top:20px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0;color:#666;font-size:13px;'>Open the lead in the CRM portal to log your follow-up and update the status.</p>
    </div>
    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>RankBuilder CRM · Powered by AgenticFlows</p>
  </div>
</body>
</html>"""


def main():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due = (
            db.query(LeadReminder)
            .filter(LeadReminder.status == "PENDING", LeadReminder.remind_at <= now)
            .all()
        )
        if not due:
            log.info("No due reminders")
            return

        for r in due:
            lead = db.query(Lead).filter(Lead.id == r.lead_id).first()
            if not lead:
                r.status = "DISMISSED"
                continue

            to_email = lead.assigned_to or r.created_by
            to_name = lead.assigned_to_name or to_email or ""
            if not to_email:
                r.status = "DISMISSED"
                continue

            subject = f"⏰ [RankBuilder] Reminder: {lead.company_name or 'Lead'}"
            html = _template(lead, r.note, r.remind_at.strftime('%Y-%m-%d %H:%M UTC'))
            ok = _brevo_send(to_email, subject, html, to_name=to_name,
                             sender_email=SENDER_EMAIL, sender_name=SENDER_NAME,
                             lead_id=lead.id, notification_type="reminder")
            if ok:
                r.status = "SENT"
                r.sent_at = datetime.utcnow()
                log.info("Reminder sent to %s for lead %s", to_email, lead.id)
            else:
                log.error("Failed to send reminder for lead %s", lead.id)

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
