"""
RankBuilder CRM — Follow-up Reminder Checker
============================================
Runs via cron (e.g. every 30-60 min) and emails the assigned sales rep
a reminder for leads that are:
  - assigned to them
  - not yet converted/lost
  - not followed up in the last N hours (default 24)

This drives the "don't let leads go cold" workflow. Each reminder references
the lead so the rep can log their follow-up in the CRM (tracked for productivity).
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# Allow running as a standalone script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from backend.database import SessionLocal, Lead, LeadStatus

log = logging.getLogger("crm.followup")

# ── Config ─────────────────────────────────────────────────────────────────────
REMINDER_HOURS = int(os.environ.get("FOLLOW_UP_REMINDER_HOURS", "24"))
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "sales@fortressblinds.co.za")
SENDER_NAME = "Fortress Blinds Sales"


def _brevo_send(to_email, subject, html_body, to_name=""):
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": to_name}] if to_name else [{"email": to_email}],
        "htmlContent": html_body,
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
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
            log.info(f"Reminder sent to {to_email}: {result.get('messageId','')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Brevo HTTP {e.code} to {to_email}: {body[:200]}")
        return False
    except Exception as e:
        log.error(f"Brevo error to {to_email}: {e}")
        return False


def find_due_leads(db, hours=REMINDER_HOURS):
    """Leads due for follow-up: assigned, not converted/lost, no follow-up in N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    leads = (
        db.query(Lead)
        .filter(
            Lead.assigned_to.isnot(None),
            Lead.status.notin_([LeadStatus.CONVERTED, LeadStatus.LOST]),
            # Due if never followed up OR last follow-up older than cutoff
            (Lead.last_follow_up_at.is_(None)) | (Lead.last_follow_up_at < cutoff),
        )
        .all()
    )
    return leads


def main():
    if not BREVO_API_KEY:
        log.warning("BREVO_API_KEY not set — skipping follow-up reminders")
        return

    db = SessionLocal()
    try:
        due = find_due_leads(db)
        if not due:
            log.info("No leads due for follow-up")
            return

        # Group by assigned rep
        from collections import defaultdict
        by_rep = defaultdict(list)
        for lead in due:
            by_rep[(lead.assigned_to, lead.assigned_to_name or lead.assigned_to)].append(lead)

        for (rep_email, rep_name), leads in by_rep.items():
            rows = ""
            for l in leads[:10]:
                loc = l.location or "Unknown area"
                name = l.contact_name or l.company_name or "Lead"
                last_fu = l.last_follow_up_at.strftime("%Y-%m-%d") if l.last_follow_up_at else "Never"
                rows += f"""
                <tr>
                    <td style='padding:8px;border:1px solid #eee;'>{name}</td>
                    <td style='padding:8px;border:1px solid #eee;'>{loc}</td>
                    <td style='padding:8px;border:1px solid #eee;'>{l.contact_phone or '—'}</td>
                    <td style='padding:8px;border:1px solid #eee;'>{last_fu}</td>
                </tr>"""

            subject = f"⏰ [RankBuilder] {len(leads)} lead(s) due for follow-up"
            html = f"""
            <!DOCTYPE html><html><body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
            <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
              <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
                <h1 style='margin:0;font-size:20px;color:#333;'>⏰ Follow-up Reminder</h1>
                <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
              </div>
              <p style='color:#555;font-size:14px;'>You have <strong>{len(leads)}</strong> lead(s) that haven't been followed up in over {REMINDER_HOURS} hours:</p>
              <table style='width:100%;border-collapse:collapse;margin:16px 0;'>
                <tr style='background:#f5f5f5;'>
                  <th style='padding:8px;border:1px solid #eee;text-align:left;'>Lead</th>
                  <th style='padding:8px;border:1px solid #eee;text-align:left;'>Area</th>
                  <th style='padding:8px;border:1px solid #eee;text-align:left;'>Phone</th>
                  <th style='padding:8px;border:1px solid #eee;text-align:left;'>Last Follow-up</th>
                </tr>
                {rows}
              </table>
              <p style='color:#666;font-size:13px;'>Log your follow-up in the CRM portal so your activity is tracked.</p>
            </div></body></html>
            """
            _brevo_send(rep_email, subject, html, to_name=rep_name)
            log.info(f"Sent {len(leads)} reminders to {rep_email}")

    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
