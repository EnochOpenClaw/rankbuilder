"""
RankBuilder CRM — HOS Sales Team Group Migration
================================================
Adds the House of Supreme "Sales Team" notification group with the 4 reps
(Lee-Ann, Robin, Tiaan, Vanessa) so all of them are notified on new leads.

Also creates the new tables (lead_activities, email_logs, notification_groups)
and the group_id column on notification_settings if they don't exist yet.

Uses raw SQLite so it runs identically against the live VPS DB.
Run on VPS:  python3 /root/rankbuilder/crm/backend/migrate_hos_groups.py
             (or with CRM_DB env override)
"""

import sqlite3
import sys
import os
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("CRM_DB", "/root/rankbuilder/crm/data/rankbuilder_crm.db")

# House of Supreme Sales Team — all 4 notified on new leads
HOS_SALES_TEAM = [
    ("lee-ann@houseofsupreme.co.za", "Lee-Ann Van Zyl"),
    ("robin@houseofsupreme.co.za", "Robin Bras"),
    ("tiaan@houseofsupreme.co.za", "Tiaan van der Walt"),
    ("vanessa@houseofsupreme.co.za", "Vanessa Bras"),
]


def _ensure_column(c, table, column, ddl):
    """Add a column to an existing table if it doesn't already exist."""
    c.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in c.fetchall()]
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        print(f"✅ Added column: {table}.{column}")
        return True
    print(f"ℹ️  Column already exists: {table}.{column}")
    return False


def _table_exists(c, table):
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return c.fetchone() is not None


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB not found at {DB_PATH}. Set CRM_DB env var if different.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── 1. Add group_id to notification_settings if missing ────────────────
    if _table_exists(c, "notification_settings"):
        _ensure_column(c, "notification_settings", "group_id", "VARCHAR(36)")

    # ── 2. Create new tables if missing ─────────────────────────────────────
    # notification_groups
    if not _table_exists(c, "notification_groups"):
        c.execute("""
            CREATE TABLE notification_groups (
                id VARCHAR(36) PRIMARY KEY,
                client_id VARCHAR(36) NOT NULL,
                name VARCHAR(100) NOT NULL,
                description VARCHAR(255),
                created_at DATETIME
            )
        """)
        print("✅ Created table: notification_groups")
    else:
        print("ℹ️  Table already exists: notification_groups")

    # lead_activities (stacked follow-up log)
    if not _table_exists(c, "lead_activities"):
        c.execute("""
            CREATE TABLE lead_activities (
                id VARCHAR(36) PRIMARY KEY,
                lead_id VARCHAR(36) NOT NULL,
                activity_type VARCHAR(20) NOT NULL,
                outcome VARCHAR(20),
                note TEXT,
                occurred_at DATETIME,
                created_at DATETIME,
                created_by VARCHAR(255)
            )
        """)
        print("✅ Created table: lead_activities")
    else:
        print("ℹ️  Table already exists: lead_activities")

    # email_logs (short-term manual email capture)
    if not _table_exists(c, "email_logs"):
        c.execute("""
            CREATE TABLE email_logs (
                id VARCHAR(36) PRIMARY KEY,
                lead_id VARCHAR(36) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                subject VARCHAR(500),
                body TEXT,
                from_email VARCHAR(255),
                to_email VARCHAR(255),
                sent_at DATETIME,
                created_at DATETIME,
                created_by VARCHAR(255)
            )
        """)
        print("✅ Created table: email_logs")
    else:
        print("ℹ️  Table already exists: email_logs")

    # ── 3. Create/verify the HOS Sales Team group ──────────────────────────
    # Find the HOS client
    c.execute("SELECT id FROM clients WHERE company_name='House of Supreme' ORDER BY created_at LIMIT 1")
    row = c.fetchone()
    if not row:
        print("❌ House of Supreme client not found. Run reseed_full.py first.")
        conn.close()
        sys.exit(1)
    client_id = row[0]

    # Check if Sales Team group exists
    c.execute("SELECT id FROM notification_groups WHERE client_id=? AND name='Sales Team'", (client_id,))
    group_row = c.fetchone()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

    if group_row:
        group_id = group_row[0]
        print(f"ℹ️  Sales Team group already exists (id={group_id})")
        # Ensure all 4 members present
        c.execute("SELECT target FROM notification_settings WHERE group_id=?", (group_id,))
        existing = {r[0] for r in c.fetchall()}
        added = 0
        for target, name in HOS_SALES_TEAM:
            if target not in existing:
                c.execute(
                    "INSERT INTO notification_settings (id, client_id, group_id, notification_type, target, name, enabled, created_at) "
                    "VALUES (?, ?, ?, 'EMAIL', ?, ?, 1, ?)",
                    (str(uuid.uuid4()), client_id, group_id, target, name, now),
                )
                added += 1
        if added:
            print(f"✅ Added {added} missing members to Sales Team group")
        else:
            print("ℹ️  All 4 members already present")
    else:
        group_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO notification_groups (id, client_id, name, description, created_at) "
            "VALUES (?, ?, 'Sales Team', ?, ?)",
            (group_id, client_id,
             "House of Supreme sales reps — notified on all new leads", now),
        )
        print(f"✅ Created Sales Team group (id={group_id})")
        for target, name in HOS_SALES_TEAM:
            c.execute(
                "INSERT INTO notification_settings (id, client_id, group_id, notification_type, target, name, enabled, created_at) "
                "VALUES (?, ?, ?, 'EMAIL', ?, ?, 1, ?)",
                (str(uuid.uuid4()), client_id, group_id, target, name, now),
            )
            print(f"   - {name} <{target}>")

    conn.commit()
    conn.close()
    print("\n✅ HOS Sales Team group migration complete.")


if __name__ == "__main__":
    migrate()
