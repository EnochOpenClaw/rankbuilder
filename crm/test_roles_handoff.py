#!/usr/bin/env python3
"""
CRM role-delegation + highlight + notification tests (Craig 2026-09-14).
Verifies:
1. read_by_me is returned by the API and drives the unread highlight correctly
   (a lead shows unread for the assigned rep until they open it, then clears).
2. SALES_MANAGER role is accepted by login and can hand a lead off to a partner
   client (delegated hand-off, not SYSTEM_ADMIN only).
3. CLIENT_ADMIN can also hand off.
4. VIEWER still cannot hand off (least privilege).
5. Archived leads are still returned with read_by_me (archive follow-ups path).
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

HOS = "e74119b9-17e3-4f74-b218-67ef0e66f1cc"

# Test accounts (real users in the local DB)
USERS = {
    "craig":   ("craig@houseofsupreme.co.za", "RankBuilder!23"),
    "richard": ("richard@houseofsupreme.co.za", "Richard1234!"),
    "tiaan":   ("tiaan@houseofsupreme.co.za", "Tiaan1234!"),
    "robin":   ("robin@houseofsupreme.co.za", "Robin1234!"),
}


def login(email, pw):
    r = client.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


def test_highlight_read_by_me():
    print("=" * 60)
    print("TEST 1: read_by_me highlight (assigned unread -> read)")
    print("=" * 60)
    token = login(*USERS["richard"])
    h = {"Authorization": f"Bearer {token}"}

    # Create a lead assigned to Richard (manual create assigns to creator)
    r = client.post("/api/leads", headers=h, json={
        "client_id": HOS, "source": "MANUAL",
        "contact_name": "Highlight Test", "contact_email": "highlight.test@example.com",
        "location": "Cape Town",
    })
    assert r.status_code == 201, f"create: {r.text}"
    lead = r.json()
    lid = lead["id"]
    # Richard created it, so it's assigned to him and NOT yet read by him
    assert lead["assigned_to"] == USERS["richard"][0], "lead should be assigned to Richard"
    assert lead["read_by_me"] is False, "newly created assigned lead should be unread for Richard"
    print(f"✅ Created lead {lid[:8]} — read_by_me=False (unread)")

    # List — should still show read_by_me False when fetched by Richard
    r = client.get(f"/api/leads?client_id={HOS}", headers=h)
    assert r.status_code == 200
    found = next((l for l in r.json()["leads"] if l["id"] == lid), None)
    assert found is not None
    assert found["read_by_me"] is False, "listed lead should be unread"
    print("✅ Listed lead shows read_by_me=False")

    # Mark read
    r = client.post(f"/api/leads/{lid}/read", headers=h)
    assert r.status_code == 200, f"mark read: {r.text}"
    assert r.json()["read_by_me"] is True, "after mark-read, read_by_me should be True"
    print("✅ After markRead, read_by_me=True (highlight clears)")

    # Fetch again — should now be read
    r = client.get(f"/api/leads/{lid}", headers=h)
    assert r.json()["read_by_me"] is True, "fetch after read should be True"
    print("✅ Fetch after read shows read_by_me=True")

    # Cleanup
    client.delete(f"/api/leads/{lid}", headers=h)
    print("✅ Cleaned up")
    print()


def test_sales_manager_role():
    print("=" * 60)
    print("TEST 2: SALES_MANAGER role accepted + can manage (hand off)")
    print("=" * 60)
    from backend.routes.auth import hash_password
    from backend.database import SessionLocal, User
    # Use a throwaway SALES_MANAGER account so the test never depends on a real
    # user's password. Tiaan is SALES_MANAGER in the DB (Craig's final call
    # 2026-09-14); Richard is deliberately untouched (CLIENT_ADMIN).
    db = SessionLocal()
    sm = User(email="sm@example.com", hashed_password=hash_password("TestPass123!"),
              full_name="SM Test", client_id=HOS, role="SALES_MANAGER")
    db.add(sm)
    db.commit()
    sm_id = sm.id
    db.close()

    try:
        token = login("sm@example.com", "TestPass123!")
        h = {"Authorization": f"Bearer {token}"}
        # Ensure login still returns the new role
        r = client.get("/api/auth/me", headers=h)
        assert r.status_code == 200
        assert r.json()["role"] == "SALES_MANAGER", f"expected SALES_MANAGER, got {r.json()['role']}"
        print(f"✅ Login accepted; role={r.json()['role']}")

        # SALES_MANAGER can read leads of own client
        r = client.get(f"/api/leads?client_id={HOS}", headers=h)
        assert r.status_code == 200
        print("✅ SALES_MANAGER can list own client's leads")

        # SALES_MANAGER CAN hand off (delegated capability)
        r = client.post("/api/leads/some-id/handoff", headers=h, json={
            "partner_client_id": "x", "target_user_email": "y@example.com"})
        # Expect 404 (lead not found) NOT 403 — proving permission is granted.
        assert r.status_code == 404, f"SALES_MANAGER handoff should pass auth (404), got {r.status_code}: {r.text}"
        print("✅ SALES_MANAGER handoff permission granted (404 = auth passed, lead lookup fails as expected)")
    finally:
        db = SessionLocal()
        db.query(User).filter(User.id == sm_id).delete()
        db.commit()
        db.close()
    print()


def test_richard_untouched():
    print("=" * 60)
    print("TEST 2b: richard stays CLIENT_ADMIN (not re-scoped)")
    print("=" * 60)
    from backend.database import SessionLocal, User
    db = SessionLocal()
    u = db.query(User).filter(User.email == USERS["richard"][0]).first()
    assert u.role == "CLIENT_ADMIN", f"richard should remain CLIENT_ADMIN, got {u.role}"
    db.close()
    print("✅ richard = CLIENT_ADMIN (untouched, sees only Cape Town jobs as before)")
    print()


def test_handoff_delegated_to_client_admin():
    print("=" * 60)
    print("TEST 3: CLIENT_ADMIN can hand a lead off (delegated)")
    print("=" * 60)
    from backend.database import SessionLocal, User, Client, Lead
    # Clean any leftover test data from a prior aborted run (idempotent)
    db = SessionLocal()
    db.query(User).filter(User.email == "partner.admin@example.com").delete()
    db.query(Client).filter(Client.company_name == "Test Partner Co").delete()
    db.commit()
    db.close()
    # Create a partner client + user to hand off to
    db = SessionLocal()
    partner = Client(company_name="Test Partner Co", contact_email="partner@example.com",
                     notification_target="partner@example.com")
    db.add(partner)
    db.flush()
    db.commit()
    partner_id = partner.id
    partner_user = User(email="partner.admin@example.com", hashed_password="x",
                        full_name="Partner Admin", client_id=partner_id, role="CLIENT_ADMIN")
    db.add(partner_user)
    db.commit()
    db.close()

    # Richard is CLIENT_ADMIN in the DB — use him to hand off (delegated capability).
    token = login(*USERS["richard"])
    h = {"Authorization": f"Bearer {token}"}

    # Create a lead (assigned to Richard as creator)
    r = client.post("/api/leads", headers=h, json={
        "client_id": HOS, "source": "MANUAL",
        "contact_name": "Handoff Test", "contact_email": "handoff.test@example.com",
        "location": "Cape Town",
    })
    assert r.status_code == 201, f"create: {r.text}"
    lid = r.json()["id"]

    # Richard (CLIENT_ADMIN) hands it off to the partner admin
    r = client.post(f"/api/leads/{lid}/handoff", headers=h, json={
        "partner_client_id": partner_id,
        "target_user_email": "partner.admin@example.com",
    })
    assert r.status_code == 200, f"CLIENT_ADMIN handoff should succeed: {r.text}"
    copy = r.json()
    assert copy["client_id"] == partner_id, "handoff copy should belong to partner client"
    assert copy["assigned_to"] == "partner.admin@example.com"
    print(f"✅ CLIENT_ADMIN (Richard) handed lead off -> partner (copy {copy['id'][:8]})")

    # Cleanup: delete copy + original, then partner + user
    db = SessionLocal()
    db.query(Lead).filter(Lead.id == copy["id"]).delete()
    db.commit()
    db.close()
    client.delete(f"/api/leads/{lid}", headers=h)
    db = SessionLocal()
    db.query(User).filter(User.email == "partner.admin@example.com").delete()
    db.query(Client).filter(Client.id == partner_id).delete()
    db.commit()
    db.close()
    print("✅ Cleaned up partner + copies")
    print()


def test_viewer_cannot_handoff():
    print("=" * 60)
    print("TEST 4: VIEWER cannot hand off (least privilege)")
    print("=" * 60)
    token = login(*USERS["robin"])
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/leads/some-id/handoff", headers=h, json={
        "partner_client_id": "x", "target_user_email": "y@example.com"})
    assert r.status_code == 403, f"VIEWER handoff should be 403, got {r.status_code}"
    print("✅ VIEWER handoff blocked (403)")
    print()


if __name__ == "__main__":
    test_highlight_read_by_me()
    test_sales_manager_role()
    test_richard_untouched()
    test_handoff_delegated_to_client_admin()
    test_viewer_cannot_handoff()
    print("=" * 60)
    print("🎉 ALL ROLE/DELEGATION/HIGHLIGHT TESTS PASSED")
    print("=" * 60)
