"""
RankBuilder CRM — Post-Install Follow-Up
==========================================
Runs via cron (daily) and fires the post-install follow-up for leads whose
payment was received PAYMENT_FOLLOWUP_DAYS ago (default 7 days / 1 week).

Lifecycle: lead → quote → payment RECEIVED → install/quiet window (7 days)
→ post-install follow-up (customer + rep) → done.

Two emails fire at the same time:
  1. CUSTOMER  — warm "how did the install go?" + review/testimonial ask,
                 sent from the validated Brevo sender (ai@fortressblinds.co.za)
                 with display name "House of Supreme".
  2. REP       — a check-in call task so the assigned rep follows up personally.

A lead is "due" when:
  - payment_status == RECEIVED
  - payment_received_at is set and is >= PAYMENT_FOLLOWUP_DAYS ago
  - post_install_followup_sent_at is NULL (not yet sent)
  - not handed off to a partner

After sending, post_install_followup_sent_at is set so it never re-fires.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone

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

from backend.database import SessionLocal, Lead

log = logging.getLogger("crm.postinstall")

# ── Config ───────────────────────────────────────────────────────────────────
# Days after payment received to send the post-install follow-up (default 7).
PAYMENT_FOLLOWUP_DAYS = int(os.environ.get("PAYMENT_FOLLOWUP_DAYS", "7"))

# Sender: must be a VALIDATED Brevo sender. Only ai@fortressblinds.co.za is
# validated (sales@/craig@ were rejected by Brevo on 2026-08-05). We brand the
# display name as "House of Supreme" so it reads correctly to the customer.
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "ai@fortressblinds.co.za")
SENDER_NAME = os.environ.get("POST_INSTALL_SENDER_NAME", "House of Supreme")

# Review / testimonial ask — where customers leave reviews (Google/Facebook).
REVIEW_URL = os.environ.get("REVIEW_URL", "")

from backend.notifications import _brevo_send


def _customer_email(lead, days):
    company = lead.company_name or "your new installation"
    contact = lead.contact_name or "there"
    review_block = ""
    if REVIEW_URL:
        review_block = f"""
    <div style='margin-top:20px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0 0 8px;color:#333;font-size:14px;'><strong>Enjoying your new installation?</strong></p>
      <p style='margin:0 0 12px;color:#666;font-size:13px;'>We'd love a quick review — it helps other homeowners find us.</p>
      <a href='{REVIEW_URL}' style='display:inline-block;background:#1677ff;color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;font-size:14px;'>Leave a review</a>
    </div>"""
    return f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>Thank you, {contact}!</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>House of Supreme · {datetime.now(timezone.utc).strftime('%d %B %Y')}</p>
    </div>
    <p style='color:#333;font-size:14px;'>It's been about <strong>{days} days</strong> since your {company} was installed. We hope everything is working perfectly and you're loving the result.</p>
    <p style='color:#555;font-size:14px;'>If there's anything at all that needs attention — a tweak, a question, or a follow-up — please just reply to this email and we'll take care of it right away.</p>
    {review_block}
    <p style='margin:20px 0 0;color:#555;font-size:14px;'>Thank you for choosing House of Supreme.</p>
    <p style='margin:4px 0 0;color:#888;font-size:13px;'>The House of Supreme Team</p>
    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>House of Supreme · Powered by RankBuilder CRM</p>
  </div>
</body>
</html>"""


def _rep_email(lead, days):
    company = lead.company_name or "the lead"
    contact = lead.contact_name or "—"
    phone = lead.contact_phone or "—"
    location = lead.location or "—"
    return f"""
<!DOCTYPE html>
<html>
<body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fafafa;'>
  <div style='background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
    <div style='border-bottom:2px solid #f0f0f0;padding-bottom:16px;margin-bottom:20px;'>
      <h1 style='margin:0;font-size:20px;color:#333;'>📞 Post-Install Check-In</h1>
      <p style='margin:8px 0 0;color:#888;font-size:13px;'>RankBuilder CRM · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
    <p style='color:#333;font-size:14px;'>It's been <strong>{days} days</strong> since payment was received for this job. Please do a quick post-install check-in call:</p>
    <div style='background:#f0f4ff;border:1px solid #dbe4ff;border-radius:8px;padding:16px;margin:16px 0;'>
      <h2 style='margin:0 0 12px;font-size:18px;color:#111;'>{company}</h2>
      <table style='width:100%;border-collapse:collapse;font-size:14px;color:#444;'>
        <tr><td style='padding:4px 0;width:110px;color:#888;'>Contact</td><td>{contact}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Phone</td><td>{phone}</td></tr>
        <tr><td style='padding:4px 0;color:#888;'>Area</td><td>{location}</td></tr>
      </table>
    </div>
    <div style='margin-top:20px;padding:16px;background:#eef2ff;border-radius:8px;text-align:center;'>
      <p style='margin:0;color:#666;font-size:13px;'>Confirm the install went well, ask if they need anything, and invite a review. Log the outcome in the CRM.</p>
    </div>
    <p style='margin:20px 0 0;color:#aaa;font-size:11px;text-align:center;'>RankBuilder CRM · House of Supreme · Powered by AgenticFlows</p>
  </div>
</body>
</html>"""


def main():
    if not os.environ.get("BREVO_API_KEY"):
        log.warning("BREVO_API_KEY not set — skipping post-install follow-up")
        return

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=PAYMENT_FOLLOWUP_DAYS)

        due = (
            db.query(Lead)
            .filter(
                Lead.payment_status == "RECEIVED",
                Lead.payment_received_at.isnot(None),
                Lead.payment_received_at <= cutoff,
                Lead.post_install_followup_sent_at.is_(None),
                Lead.partner_handoff_id.is_(None),
            )
            .all()
        )

        if not due:
            log.info("No post-install follow-ups due")
            return

        sent = 0
        for lead in due:
            # Compute actual days since payment (for the email copy)
            pr = lead.payment_received_at
            if pr.tzinfo is None:
                pr = pr.replace(tzinfo=timezone.utc)
            days = max(1, int((now - pr).total_seconds() // 86400))

            # 1) Customer email (if we have an address)
            if lead.contact_email:
                _brevo_send(
                    lead.contact_email,
                    f"Thank you — how is your {lead.company_name or 'installation'}?",
                    _customer_email(lead, days),
                    to_name=lead.contact_name or "",
                    sender_email=SENDER_EMAIL,
                    sender_name=SENDER_NAME,
                    lead_id=lead.id,
                    notification_type="post_install_followup",
                )

            # 2) Rep check-in email (if assigned)
            if lead.assigned_to:
                _brevo_send(
                    lead.assigned_to,
                    f"📞 [RankBuilder] Post-Install Check-In: {lead.company_name or 'Lead'}",
                    _rep_email(lead, days),
                    to_name=lead.assigned_to_name or "",
                    sender_email=SENDER_EMAIL,
                    sender_name="RankBuilder CRM",
                    lead_id=lead.id,
                    notification_type="post_install_followup",
                )

            lead.post_install_followup_sent_at = datetime.utcnow()
            db.add(lead)
            sent += 1

        db.commit()
        log.info("Post-install follow-ups sent: %d", sent)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
