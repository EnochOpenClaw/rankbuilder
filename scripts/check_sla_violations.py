"""
RankBuilder CRM SLA Violation Monitor - cron every 30 min
Flags leads breaching response-time SLAs, emails assigned agent.
Rules: NEW reviewed in 4h, QUALIFIED sent in 24h, SENT contacted in 48h, stale after 3d.
"""
import os, sys, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE.parent / "crm"))
os.chdir(str(_HERE.parent / "crm"))

def _load_env():
    ep = _HERE.parent / ".env"
    if not ep.is_file(): return
    for line in open(ep):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        k = k.strip(); v = v.strip().strip(chr(34)).strip(chr(39))
        if k and k not in os.environ: os.environ[k] = v
_load_env()

from backend.database import SessionLocal, Lead
from backend.notifications import _brevo_send, _get_notification_recipients
log = logging.getLogger("sla_monitor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

NH = int(os.environ.get("SLA_NEW_HOURS", "4"))
QH = int(os.environ.get("SLA_QUALIFIED_HOURS", "24"))
SH = int(os.environ.get("SLA_SENT_HOURS", "48"))
SD = int(os.environ.get("SLA_STALE_DAYS", "3"))
COOLDOWN_H = int(os.environ.get("SLA_ALERT_COOLDOWN_HOURS", "12"))  # min hours between alerts per lead
# ── Payment-received quiet window ────────────────────────────────────────────
# Once a lead's payment is RECEIVED (job won, install in progress), suppress SLA
# breach alerts for this many days. Default 7 days (1 week).
PAYMENT_QUIET_DAYS = int(os.environ.get("PAYMENT_QUIET_DAYS", "7"))
SENDER = os.environ.get("SENDER_EMAIL", "ai@fortressblinds.co.za")

def _h(dt):
    if not dt: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0

def check_sla(db):
    out = []
    now = datetime.utcnow()
    cnew = now - timedelta(hours=NH)
    cstale = now - timedelta(days=SD)
    for lead in db.query(Lead).filter(
        Lead.conversion_status.is_(None),
        Lead.partner_handoff_id.is_(None),
        Lead.status.notin_(["CONVERTED", "LOST"]),  # terminal deals stop pinging
        Lead.archived == 0,  # archived deals stop pinging
    ).all():
        # (skip leads handed off to a partner — they're no longer this rep's to action)
        # ── Payment-received quiet window ──────────────────────────────────
        # If payment was received within the last PAYMENT_QUIET_DAYS, the job is
        # in install/production — don't fire SLA breach alerts during that window.
        if lead.payment_status == "RECEIVED" and lead.payment_received_at:
            pr = lead.payment_received_at
            if pr.tzinfo is None:
                pr = pr.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - pr).total_seconds() < PAYMENT_QUIET_DAYS * 86400:
                continue  # in quiet window — skip SLA alerts
        st = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
        if st == "NEW":
            if lead.created_at and lead.created_at < cnew and not lead.follow_up_count:
                out.append((lead, "NEW not reviewed", "%dh since created" % _h(lead.created_at)))
        elif st == "QUALIFIED":
            if not lead.sent_to_client_at and (_h(lead.updated_at) or 0) > QH:
                out.append((lead, "QUALIFIED not sent", "%dh since qualify" % _h(lead.updated_at)))
        elif st == "SENT":
            la = lead.last_follow_up_at or lead.sent_to_client_at or lead.updated_at
            if (_h(la) or 0) > SH:
                out.append((lead, "SENT no follow-up", "%dh since activity" % _h(la)))
        if lead.last_follow_up_at and lead.last_follow_up_at < cstale and st != "NEW":
            out.append((lead, "Stale no activity", "%dd since contact" % (now - lead.last_follow_up_at).days))
    return out

def should_alert(lead):
    from datetime import timedelta as _td
    if not lead.last_sla_alert_at: return True
    la = lead.last_sla_alert_at
    if la.tzinfo is None: la = la.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - la) >= _td(hours=COOLDOWN_H)


def notify(db, lead, rule, detail):
    co = lead.company_name or lead.contact_name or "Lead"
    sc = lead.quality_score or 0
    tier = "HOT" if sc >= 70 else "WARM" if sc >= 40 else "COLD"
    subject = "SLA Breach: %s - %s" % (co, rule)
    body = "<h2>SLA Breach - %s</h2><p>%s</p>" % (rule, detail)
    body += "<table><tr><td>Company</td><td>%s</td></tr>" % co
    body += "<tr><td>Contact</td><td>%s</td></tr>" % (lead.contact_name or "-")
    body += "<tr><td>Phone</td><td>%s</td></tr>" % (lead.contact_phone or "-")
    body += "<tr><td>Score</td><td>%s %s</td></tr></table>" % (tier, sc)
    body += "<p>Action this lead promptly so it does not go cold.</p>"

    # Build recipient set: assigned rep + notification group (+ default rep if unassigned)
    recipients = set()
    if lead.assigned_to:
        recipients.add((lead.assigned_to, lead.assigned_to_name or "Rep"))
    else:
        from backend.assignment import resolve_rep_for_location
        drep, dname = resolve_rep_for_location(lead.location)
        recipients.add((drep, dname))
    for email, name in _get_notification_recipients(lead.client_id, db) or []:
        recipients.add((email, name))

    sent = 0
    for email, name in recipients:
        try:
            _brevo_send(email, subject, body, to_name=name,
                        sender_email=SENDER, sender_name="RankBuilder CRM",
                        lead_id=lead.id, notification_type="sla_breach")
            sent += 1
        except Exception as e:
            log.error("SLA alert fail to %s: %s", email, e)
    if sent:
        lead.last_sla_alert_at = datetime.utcnow()
        db.commit()
        log.info("SLA alerts sent to %d recipients for %s (%s)", sent, co, rule)


def main():
    db = SessionLocal()
    try:
        v = check_sla(db)
        log.info("SLA violations: %d", len(v))
        for lead, rule, detail in v:
            if should_alert(lead): notify(db, lead, rule, detail)
    finally:
        db.close()

if __name__ == "__main__":
    main()
