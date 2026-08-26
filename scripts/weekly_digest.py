#!/usr/bin/env python3
"""
RankBuilder CRM — Weekly Management Digest
Compiles the week's key metrics and emails a summary to management.

Run via cron, e.g. Monday 07:00:
  0 7 * * 1 cd /root/rankbuilder && /root/rankbuilder/venv/bin/python3 scripts/weekly_digest.py >> /root/rankbuilder/logs/weekly_digest.log 2>&1

Recipients: HOS management (Robin, Vanessa, Lee-Ann) + Craig.
"""
import os
import sys
import logging
from datetime import datetime, timedelta

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
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_env_file()

from backend.database import SessionLocal, Lead, LeadActivity
from backend.notifications import _brevo_send

log = logging.getLogger("crm.digest")

# HOS management recipients
RECIPIENTS = [
    ("craig@houseofsupreme.co.za", "Craig Pauls"),
    ("robin@houseofsupreme.co.za", "Robin Bras"),
    ("vanessa@houseofsupreme.co.za", "Vanessa Bras"),
    ("lee-ann@houseofsupreme.co.za", "Lee-Ann Van Zyl"),
]
HOS_CLIENT = "514a96af-4262-4cfe-b85e-37b6af223faa"


def _fmt_hours(h):
    if h is None:
        return "—"
    if h < 1:
        return f"{int(round(h*60))}m"
    if h < 24:
        return f"{round(h*10)/10}h"
    return f"{int(h//24)}d {int(round(h%24))}h"


def build_digest(db):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    leads = (
        db.query(Lead)
        .filter(Lead.client_id == HOS_CLIENT, Lead.created_at >= week_ago)
        .all()
    )
    total = len(leads)
    qualified = sum(1 for l in leads if (l.status.value if hasattr(l.status, "value") else str(l.status)) in ("QUALIFIED", "SENT", "CONTACTED", "CONVERTED"))
    converted = sum(1 for l in leads if l.conversion_status == "CONVERTED")
    lost = sum(1 for l in leads if l.conversion_status == "LOST")

    # Response time (first activity - creation) for this week's leads
    ids = [l.id for l in leads]
    first_act = {}
    if ids:
        acts = (
            db.query(LeadActivity.lead_id, LeadActivity.occurred_at)
            .filter(LeadActivity.lead_id.in_(ids))
            .order_by(LeadActivity.occurred_at.asc())
            .all()
        )
        seen = set()
        for lid, occ in acts:
            if lid not in seen:
                first_act[lid] = occ
                seen.add(lid)
    resp_times = []
    uncontacted = 0
    for l in leads:
        fa = first_act.get(l.id)
        if l.created_at and fa:
            h = (fa - l.created_at).total_seconds() / 3600.0
            if h >= 0:
                resp_times.append(h)
                continue
        if (l.status.value if hasattr(l.status, "value") else str(l.status)) != "NEW":
            uncontacted += 1
    avg_resp = round(sum(resp_times) / len(resp_times), 1) if resp_times else None
    resp_rate = round(len(resp_times) / total * 100, 1) if total else 0.0

    # Per-agent activity
    acts = db.query(LeadActivity).filter(LeadActivity.lead_id.in_(ids)).all() if ids else []
    by_agent = {}
    for a in acts:
        who = a.created_by or "unknown"
        by_agent[who] = by_agent.get(who, 0) + 1
    top_agent = max(by_agent, key=by_agent.get) if by_agent else "—"

    return {
        "total": total,
        "qualified": qualified,
        "converted": converted,
        "lost": lost,
        "conv_rate": round(converted / total * 100, 1) if total else 0.0,
        "avg_resp": avg_resp,
        "resp_rate": resp_rate,
        "uncontacted": uncontacted,
        "activity": sum(by_agent.values()),
        "top_agent": top_agent,
        "week": f"{week_ago.strftime('%d %b')} – {now.strftime('%d %b %Y')}",
    }


def main():
    db = SessionLocal()
    try:
        d = build_digest(db)
        subject = f"📊 RankBuilder Weekly Digest — {d['week']}"
        html = f"""
<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#fafafa;">
  <div style="background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <h2 style="margin:0 0 4px;">Weekly Performance Digest</h2>
    <p style="margin:0 0 16px;color:#888;font-size:13px;">House of Supreme · {d['week']}</p>

    <table style="width:100%;border-collapse:collapse;margin:8px 0;">
      <tr>
        <td style="padding:10px;background:#eef2ff;border-radius:8px;width:25%;text-align:center;"><div style="font-size:24px;font-weight:700;">{d['total']}</div><div style="font-size:11px;color:#666;">Leads</div></td>
        <td style="padding:10px;width:4%;"></td>
        <td style="padding:10px;background:#eef2ff;border-radius:8px;width:25%;text-align:center;"><div style="font-size:24px;font-weight:700;color:#722ed1;">{d['qualified']}</div><div style="font-size:11px;color:#666;">Qualified</div></td>
        <td style="padding:10px;width:4%;"></td>
        <td style="padding:10px;background:#eef2ff;border-radius:8px;width:25%;text-align:center;"><div style="font-size:24px;font-weight:700;color:#52c41a;">{d['converted']}</div><div style="font-size:11px;color:#666;">Converted ({d['conv_rate']}%)</div></td>
        <td style="padding:10px;width:4%;"></td>
        <td style="padding:10px;background:#fff1f0;border-radius:8px;width:25%;text-align:center;"><div style="font-size:24px;font-weight:700;color:#cf1322;">{d['lost']}</div><div style="font-size:11px;color:#666;">Lost</div></td>
      </tr>
    </table>

    <table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;">
      <tr><td style="padding:6px 0;color:#555;">Avg response time</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_hours(d['avg_resp'])}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Response rate</td><td style="padding:6px 0;text-align:right;font-weight:600;">{d['resp_rate']}%</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Leads un-contacted / no activity</td><td style="padding:6px 0;text-align:right;font-weight:600;color:#cf1322;">{d['uncontacted']}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Follow-up activities logged</td><td style="padding:6px 0;text-align:right;font-weight:600;">{d['activity']}</td></tr>
    </table>

    <div style="margin-top:12px;padding:12px;background:#f6ffed;border-radius:8px;font-size:13px;">
      <strong>Top agent by activity:</strong> {d['top_agent']}
    </div>

    <p style="margin:20px 0 0;color:#aaa;font-size:11px;">RankBuilder CRM · House of Supreme · Powered by AgenticFlows</p>
  </div>
</div>"""

        ok = 0
        for email, name in RECIPIENTS:
            r = _brevo_send(email, subject, html, to_name=name,
                            sender_email="ai@fortressblinds.co.za", sender_name="RankBuilder CRM")
            if r.get("success"):
                ok += 1
        log.info("Weekly digest sent to %d of %d recipients", ok, len(RECIPIENTS))
        print(f"Sent {ok} of {len(RECIPIENTS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
