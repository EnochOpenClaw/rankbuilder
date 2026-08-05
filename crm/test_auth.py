#!/usr/bin/env python3
"""
Authorization + Client Portal tests for the CRM.
Verifies:
1. Unauthenticated access is rejected (401)
2. VIEWER is read-only (can read own leads, cannot write, cannot access other clients)
3. CLIENT_ADMIN can read/write their own client
4. Client scoping (a user of one client cannot access another client's data)
5. Agent service token still works (create/update lead)
6. Campaigns + dashboard are scoped correctly
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

HOS_CLIENT_ID = "e74119b9-17e3-4f74-b218-67ef0e66f1cc"

# Test accounts
USERS = {
    "admin": {"email": "craig@houseofsupreme.co.za", "password": "RankBuilder!23"},
    "viewer": {"email": "robin@houseofsupreme.co.za", "password": "Robin1234!"},
}
# New long-lived agent service token (CLIENT_ADMIN, HOS client)
AGENT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMjI1YzlhNS05MjU0LTRhYWItYTIxOS1hNmZlM2E5NDAzZTUiLCJyb2xlIjoiQ0xJRU5UX0FETUlOIiwiY2xpZW50X2lkIjoiZTc0MTE5YjktMTdlMy00Zjc0LWIyMTgtNjdlZjBlNjZmMWNjIiwiZXhwIjoxOTQzNTEwMTYyfQ.2kmoSdeWT80eKKxc5o4Rf5XpM6-AN0roS509e9kmDD0"


def login(email, password):
    r = client.post("/api/auth/login",
                    data={"username": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


def test_unauth_rejected():
    print("=" * 60)
    print("TEST 1: Unauthenticated access rejected")
    print("=" * 60)
    for path in ["/api/leads", "/api/campaigns", "/api/clients",
                 f"/api/dashboard/summary?client_id={HOS_CLIENT_ID}"]:
        r = client.get(path)
        assert r.status_code == 401, f"{path} should be 401, got {r.status_code}"
    print("✅ All unauthenticated GETs return 401")
    # Write op too
    r = client.post("/api/leads", json={"client_id": HOS_CLIENT_ID, "source": "MANUAL"})
    assert r.status_code == 401, f"POST /api/leads should be 401, got {r.status_code}"
    print("✅ Unauthenticated POST returns 401")
    print()


def test_viewer_read_only():
    print("=" * 60)
    print("TEST 2: VIEWER (Robin) — read-only + client scope")
    print("=" * 60)
    token = login(USERS["viewer"]["email"], USERS["viewer"]["password"])
    h = {"Authorization": f"Bearer {token}"}

    # Can read own client's leads
    r = client.get(f"/api/leads?client_id={HOS_CLIENT_ID}", headers=h)
    assert r.status_code == 200, f"VIEWER list leads: {r.status_code} {r.text}"
    print(f"✅ VIEWER can read leads (total={r.json()['total']})")

    # Can read dashboard for own client
    r = client.get(f"/api/dashboard/summary?client_id={HOS_CLIENT_ID}", headers=h)
    assert r.status_code == 200, f"VIEWER dashboard: {r.status_code}"
    print("✅ VIEWER can read dashboard")

    # Can read campaigns for own client
    r = client.get(f"/api/campaigns?client_id={HOS_CLIENT_ID}", headers=h)
    assert r.status_code == 200
    print("✅ VIEWER can read campaigns")

    # CANNOT create a lead (read-only)
    r = client.post("/api/leads", headers=h,
                    json={"client_id": HOS_CLIENT_ID, "source": "MANUAL",
                          "contact_name": "Blocked Viewer Write"})
    assert r.status_code == 403, f"VIEWER create lead should be 403, got {r.status_code}"
    print("✅ VIEWER cannot create lead (403)")

    # CANNOT create a campaign
    r = client.post("/api/campaigns", headers=h,
                    json={"client_id": HOS_CLIENT_ID, "name": "Blocked", "channel": "HARO"})
    assert r.status_code == 403, f"VIEWER create campaign should be 403, got {r.status_code}"
    print("✅ VIEWER cannot create campaign (403)")

    # CANNOT see all clients (scoped to own only)
    r = client.get("/api/clients", headers=h)
    assert r.status_code == 200
    clients = r.json()
    assert all(c["id"] == HOS_CLIENT_ID for c in clients), "VIEWER should only see own client"
    print(f"✅ VIEWER sees only own client ({len(clients)} client(s))")
    print()


def test_admin_write():
    print("=" * 60)
    print("TEST 3: CLIENT_ADMIN (Craig) — can read/write own client")
    print("=" * 60)
    token = login(USERS["admin"]["email"], USERS["admin"]["password"])
    h = {"Authorization": f"Bearer {token}"}

    # Create a lead
    r = client.post("/api/leads", headers=h, json={
        "client_id": HOS_CLIENT_ID, "source": "MANUAL",
        "contact_name": "Portal Test Lead", "contact_email": "portal.test@example.com",
        "quality_score": 3,
    })
    assert r.status_code == 201, f"Admin create lead: {r.status_code} {r.text}"
    lead_id = r.json()["id"]
    print(f"✅ Admin created lead {lead_id[:8]}")

    # Update it
    r = client.patch(f"/api/leads/{lead_id}", headers=h, json={"status": "QUALIFIED"})
    assert r.status_code == 200, f"Admin update lead: {r.status_code}"
    assert r.json()["status"] == "QUALIFIED"
    print("✅ Admin updated lead → QUALIFIED")

    # Create a campaign
    r = client.post("/api/campaigns", headers=h, json={
        "client_id": HOS_CLIENT_ID, "name": "Portal Test Campaign", "channel": "HARO", "status": "ACTIVE",
    })
    assert r.status_code == 201, f"Admin create campaign: {r.status_code} {r.text}"
    camp_id = r.json()["id"]
    print(f"✅ Admin created campaign {camp_id[:8]}")

    # Cleanup — delete test lead + campaign
    client.delete(f"/api/leads/{lead_id}", headers=h)
    client.delete(f"/api/campaigns/{camp_id}", headers=h)
    print("✅ Cleaned up test data")
    print()


def test_agent_token():
    print("=" * 60)
    print("TEST 4: Agent service token (create/update lead)")
    print("=" * 60)
    h = {"Authorization": f"Bearer {AGENT_TOKEN}"}

    r = client.post("/api/leads", headers=h, json={
        "client_id": HOS_CLIENT_ID, "source": "HARO",
        "contact_name": "Agent Service Test", "contact_email": "agent.test@example.com",
        "company_name": "Agent Test Co", "quality_score": 4,
    })
    assert r.status_code == 201, f"Agent create lead: {r.status_code} {r.text}"
    lead_id = r.json()["id"]
    print(f"✅ Agent created lead {lead_id[:8]}")

    # Update (mark sent)
    r = client.patch(f"/api/leads/{lead_id}", headers=h, json={"status": "SENT"})
    assert r.status_code == 200, f"Agent update lead: {r.status_code}"
    assert r.json()["status"] == "SENT"
    print("✅ Agent updated lead → SENT")

    client.delete(f"/api/leads/{lead_id}", headers=h)
    print("✅ Cleaned up agent test lead")
    print()


def test_cross_client_blocked():
    print("=" * 60)
    print("TEST 5: Cross-client access blocked")
    print("=" * 60)
    # VIEWER tries to access a non-existent/other client by ID
    token = login(USERS["viewer"]["email"], USERS["viewer"]["password"])
    h = {"Authorization": f"Bearer {token}"}
    OTHER_CLIENT = "00000000-0000-0000-0000-000000000000"  # another client id
    # VIEWER passing a different client_id must be rejected (403) — scope locked
    r = client.get(f"/api/leads?client_id={OTHER_CLIENT}", headers=h)
    assert r.status_code == 403, f"Cross-client access should be 403, got {r.status_code}: {r.text}"
    print("✅ VIEWER cross-client lead list blocked (403, no leak)")

    # Omitting client_id — scopes to own client automatically
    r = client.get("/api/leads", headers=h)
    assert r.status_code == 200
    leads = r.json()["leads"]
    assert all(l["client_id"] == HOS_CLIENT_ID for l in leads), "Leads should all be HOS"
    print("✅ VIEWER omitting client_id auto-scopes to own client")

    # A different client's dashboard is blocked too
    r = client.get(f"/api/dashboard/summary?client_id={OTHER_CLIENT}", headers=h)
    assert r.status_code == 403, f"Cross-client dashboard should be 403, got {r.status_code}"
    print("✅ VIEWER cross-client dashboard blocked (403)")
    print()


if __name__ == "__main__":
    test_unauth_rejected()
    test_viewer_read_only()
    test_admin_write()
    test_agent_token()
    test_cross_client_blocked()
    print("=" * 60)
    print("🎉 ALL AUTHORIZATION/PORTAL TESTS PASSED")
    print("=" * 60)
