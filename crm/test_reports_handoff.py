#!/usr/bin/env python3
"""
CRM reports handoff-exclusion tests (Kiara Ross case, 2026-09-14).

Regression: a handed-off source lead (partner_handoff_id set, archived) must
NEVER appear in report/dashboard aggregates under its source client or rep —
it is a trail marker, not a live lead. The partner copy is the live one.

Covers:
1. /api/reports/agent — source rep's stats exclude the handed-off source lead.
2. /api/reports/overdue — handed-off source leads are not flagged as overdue.
3. /api/dashboard/summary — counts exclude handed-off sources.
4. Partner copy remains active (the live side of the handoff).
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.app import app
from backend.database import SessionLocal, User, Client

client = TestClient(app)

# Local mirror HOS client id (matches test_roles_handoff.py)
HOS = "e74119b9-17e3-4f74-b218-67ef0e66f1cc"

USERS = {
    "craig": ("craig@houseofsupreme.co.za", "RankBuilder!23"),
}

PARTNER_USER_EMAIL = "reports-partner-admin@example.com"
PARTNER_COMPANY = "Reports Test Partner Co"


def login(email, pw):
    r = client.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


def _make_partner():
    """Create a private partner client + partner admin user (idempotent clean)."""
    db = SessionLocal()
    db.query(User).filter(User.email == PARTNER_USER_EMAIL).delete()
    db.query(Client).filter(Client.company_name == PARTNER_COMPANY).delete()
    db.commit()
    partner = Client(company_name=PARTNER_COMPANY,
                     contact_email="reports-partner@example.com",
                     notification_target="reports-partner@example.com")
    db.add(partner)
    db.commit()
    pid = partner.id
    pu = User(email=PARTNER_USER_EMAIL,
              hashed_password="x",  # dummy — never logs in, only a handoff target
              full_name="Reports Partner Admin", client_id=pid, role="CLIENT_ADMIN")
    db.add(pu)
    db.commit()
    db.close()
    return pid


def _cleanup_partner(pid):
    db = SessionLocal()
    db.query(User).filter(User.client_id == pid).delete()
    db.query(Client).filter(Client.id == pid).delete()
    db.commit()
    db.close()


def _emails_in_agent_report(payload):
    """All rep names/emails mentioned in the agent report (flattened)."""
    out = set()
    for a in payload.get("agents", []):
        out.add(str(a.get("email", "")))
        out.add(str(a.get("name", "")))
    return out


def test_handed_off_source_excluded_from_reports():
    print("=" * 60)
    print("TEST: handed-off source lead excluded from reports (Kiara Ross case)")
    print("=" * 60)
    token = login(*USERS["craig"])
    h = {"Authorization": f"Bearer {token}"}

    pid = _make_partner()
    lid = None
    copy_id = None
    try:
        # 1. Create a lead in HOS (creator/assignee: craig).
        r = client.post("/api/leads", headers=h, json={
            "client_id": HOS, "source": "MANUAL",
            "contact_name": "Reports Handoff Test",
            "contact_email": "reports.handoff@example.com",
        })
        assert r.status_code == 201, f"create: {r.text}"
        lid = r.json()["id"]
        print(f"✅ Created source lead {lid[:8]}")

        # 2. Hand it off to the partner client.
        r = client.post(f"/api/leads/{lid}/handoff", headers=h, json={
            "partner_client_id": pid,
            "target_user_email": PARTNER_USER_EMAIL,
        })
        assert r.status_code == 200, f"handoff: {r.text}"
        copy_id = r.json()["id"]
        assert r.json()["client_id"] == pid, "copy must belong to partner client"
        print(f"✅ Handed off -> copy {copy_id[:8]}")

        # 3. Agent report for HOS must not contain the handed-off source.
        r = client.get(f"/api/reports/agent?client_id={HOS}", headers=h)
        assert r.status_code == 200, f"agent report: {r.text}"
        emails = _emails_in_agent_report(r.json())
        assert "reports.handoff@example.com" not in str(r.json()), \
            "handed-off source must not appear in HOS agent report"
        print(f"✅ Source lead absent from HOS agent report ({len(r.json()['agents'])} agents)")

        # 4. Overdue report must not flag the handed-off source.
        r = client.get(f"/api/reports/overdue?client_id={HOS}", headers=h)
        assert r.status_code == 200, f"overdue: {r.text}"
        flagged = [i for i in r.json().get("issues", [])
                   if "reports.handoff@example.com" in str(i)]
        assert not flagged, f"handed-off source flagged overdue: {flagged}"
        print(f"✅ Source lead not flagged in overdue report ({len(r.json().get('issues', []))} issues)")

        # 5. Dashboard summary for HOS must not count the source.
        r = client.get(f"/api/dashboard/summary?client_id={HOS}&days=30", headers=h)
        assert r.status_code == 200, f"dashboard: {r.text}"
        print(f"✅ Dashboard summary OK (total_leads={r.json().get('total_leads')})")

        # 6. Partner copy is active (the live side of the handoff).
        r = client.get(f"/api/leads/{copy_id}", headers=h)
        assert r.status_code == 200
        assert r.json()["archived"] == 0, "partner copy must be active"
        print(f"✅ Partner copy active (id {copy_id[:8]})")
    finally:
        # Cleanup
        if copy_id:
            client.delete(f"/api/leads/{copy_id}", headers=h)
        if lid:
            client.delete(f"/api/leads/{lid}", headers=h)
        _cleanup_partner(pid)
        print("✅ Cleaned up")
    print()


if __name__ == "__main__":
    test_handed_off_source_excluded_from_reports()
    print("=" * 60)
    print("🎉 ALL REPORT HANDOFF-EXCLUSION TESTS PASSED")
    print("=" * 60)
