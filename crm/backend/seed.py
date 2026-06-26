"""
Seed script — creates HOS as the first CRM client.
Run: python -m backend.seed
"""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import SessionLocal, Client, NotificationChannel

def seed():
    db = SessionLocal()
    try:
        # Check if HOS already exists
        existing = db.query(Client).filter(
            Client.company_name == "House of Supreme"
        ).first()
        if existing:
            print(f"HOS client already exists: {existing.id}")
            return

        client = Client(
            company_name="House of Supreme",
            contact_email="craig@houseofsupreme.co.za",
            notification_channel=NotificationChannel.EMAIL,
            notification_target="craig@houseofsupreme.co.za",
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        print(f"Created HOS client: {client.id}")
        print(f"  Company: {client.company_name}")
        print(f"  Email: {client.contact_email}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
