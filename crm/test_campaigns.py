#!/usr/bin/env python3
"""
Integration test for the Campaigns feature — creates, lists, updates, filters, deletes.
Uses FastAPI TestClient against the real (live) SQLite DB via the app.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # crm/
os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

HOS_CLIENT_ID = "e74119b9-17e3-4f74-b218-67ef0e66f1cc"


def login():
    r = client.post("/api/auth/login",
                    data={"username": "craig@houseofsupreme.co.za", "password": "RankBuilder!23"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def test_campaign_flow():
    token = login()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a campaign
    r = client.post("/api/campaigns", headers=headers, json={
        "client_id": HOS_CLIENT_ID,
        "name": "HARO Q3 Security Push",
        "channel": "HARO",
        "status": "ACTIVE",
    })
    assert r.status_code == 201, f"Create failed: {r.text}"
    camp = r.json()
    cid = camp["id"]
    print(f"✅ Created campaign: {camp['name']} ({cid}) channel={camp['channel']} status={camp['status']}")
    assert camp["lead_count"] == 0

    # 2. List campaigns
    r = client.get(f"/api/campaigns?client_id={HOS_CLIENT_ID}", headers=headers)
    assert r.status_code == 200, f"List failed: {r.text}"
    data = r.json()
    assert any(c["id"] == cid for c in data["campaigns"]), "Created campaign not in list"
    print(f"✅ Listed {data['total']} campaign(s)")

    # 3. Get single
    r = client.get(f"/api/campaigns/{cid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == cid
    print(f"✅ Get single campaign OK")

    # 4. Update status → PAUSED
    r = client.patch(f"/api/campaigns/{cid}", headers=headers, json={"status": "PAUSED"})
    assert r.status_code == 200, f"Update failed: {r.text}"
    assert r.json()["status"] == "PAUSED"
    print(f"✅ Updated status → PAUSED")

    # 5. Link a lead to the campaign (update an existing lead's campaign_id)
    #    First fetch a lead
    leads = client.get(f"/api/leads?client_id={HOS_CLIENT_ID}&limit=1", headers=headers).json()
    if leads["total"] > 0:
        lead = leads["leads"][0]
        lead_id = lead["id"]
        # Direct DB update to set campaign_id (no public API for it, and we're testing campaigns)
        from backend.database import SessionLocal, Lead
        db = SessionLocal()
        db.query(Lead).filter(Lead.id == lead_id).update({"campaign_id": cid})
        db.commit()
        db.close()
        # Verify campaign lead_count reflects it
        r = client.get(f"/api/campaigns/{cid}", headers=headers)
        assert r.json()["lead_count"] == 1, f"Expected 1 lead, got {r.json()['lead_count']}"
        print(f"✅ Lead linked → campaign lead_count = 1")

        # 6. Filter leads by campaign_id
        r = client.get(f"/api/leads?campaign_id={cid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["total"] == 1, f"Expected 1 filtered lead, got {r.json()['total']}"
        print(f"✅ Lead filter by campaign_id returns {r.json()['total']} lead(s)")

    # 7. Delete campaign
    r = client.delete(f"/api/campaigns/{cid}", headers=headers)
    assert r.status_code == 204, f"Delete failed: {r.text}"
    # Verify gone
    r = client.get(f"/api/campaigns/{cid}", headers=headers)
    assert r.status_code == 404, "Campaign should be gone"
    print(f"✅ Deleted campaign (now 404)")

    print("\n🎉 ALL CAMPAIGN TESTS PASSED")


if __name__ == "__main__":
    test_campaign_flow()
