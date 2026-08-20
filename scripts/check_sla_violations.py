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
from backend.notifications import _brevo_send
log = logging.getLogger("sla_monitor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

NH = int(os.environ.get("SLA_NEW_HOURS", "4"))
QH = int(os.environ.get("SLA_QUALIFIED_HOURS", "24"))
SH = int(os.environ.get("SLA_SENT_HOURS", "48"))
SD = int(os.environ.get("SLA_STALE_DAYS", "3"))
COOLDOWN_H = int(os.environ.get("SLA_ALERT_COOLDOWN_HOURS", "12"))  # min hours between alerts per lead
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
    for lead in db.query(Lead).filter(Lead.conversion_status.is_(None)).all():
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


def notify(lead, rule, detail):
    rep = lead.assigned_to
    if not rep: return
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
    try:
        _brevo_send(rep, subject, body, to_name=lead.assigned_to_name or rep,
                    sender_email=SENDER, sender_name="RankBuilder CRM")
        lead.last_sla_alert_at = datetime.utcnow()
        from backend.database import SessionLocal as _SL
        _s = _SL()
        try:
            _s.add(lead)
            _s.commit()
        finally:
            _s.close()
        log.info("SLA alert to %s for %s (%s)", rep, co, rule)
    except Exception as e:
        log.error("SLA alert fail to %s: %s", rep, e)

def main():
    db = SessionLocal()
    try:
        v = check_sla(db)
        log.info("SLA violations: %d", len(v))
        for lead, rule, detail in v:
            if should_alert(lead): notify(lead, rule, detail)
    finally:
        db.close()

if __name__ == "__main__":
    main()
