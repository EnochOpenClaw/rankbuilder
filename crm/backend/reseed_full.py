"""
RankBuilder CRM — Full Re-seed Script
Creates the HOS client (with API key), the 3 users, and a default campaign.
Run on VPS after recreating the DB: python3 /root/rankbuilder/crm/backend/reseed_full.py
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import (
    SessionLocal, Client, User, Campaign, NotificationChannel,
    LeadSource, CampaignStatus, UserRole,
)
from backend.routes.auth import hash_password

# The public API key used by WordPress / Facebook / agents
PUBLIC_API_KEY = "8c5701b7fc16e22c977601be46d6c08b7b12686c66872a34"


def reseed():
    db = SessionLocal()
    try:
        # ── Client ──────────────────────────────────────────────────────────
        client = Client(
            company_name="House of Supreme",
            contact_email="craig@houseofsupreme.co.za",
            api_key=PUBLIC_API_KEY,
            notification_channel=NotificationChannel.EMAIL,
            notification_target="craig@houseofsupreme.co.za",
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        print(f"✅ Client: {client.company_name} (id={client.id})")
        print(f"   API key: {client.api_key}")

        # ── Users ──────────────────────────────────────────────────────────
        users = [
            ("craig@houseofsupreme.co.za", "RankBuilder!23", "Craig Pauls", UserRole.SYSTEM_ADMIN),
            ("tiaan@houseofsupreme.co.za", "Tiaan1234!", "Tiaan", UserRole.CLIENT_ADMIN),
            ("robin@houseofsupreme.co.za", "Robin1234!", "Robin", UserRole.VIEWER),
        ]
        for email, pw, name, role in users:
            u = User(
                email=email,
                hashed_password=hash_password(pw),
                full_name=name,
                client_id=client.id,
                role=role,
                is_active=1,
            )
            db.add(u)
            print(f"✅ User: {email} ({role.value})")

        # ── Default campaign ───────────────────────────────────────────────
        camp = Campaign(
            client_id=client.id,
            name="HOS-Q3-Outreach",
            channel=LeadSource.GUEST_OUTREACH,
            status=CampaignStatus.ACTIVE,
        )
        db.add(camp)
        print(f"✅ Campaign: {camp.name}")

        db.commit()
        print("\n🎉 Re-seed complete!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reseed()
