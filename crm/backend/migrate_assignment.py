"""
RankBuilder CRM — DB migration: add sales rep assignment & follow-up columns
Adds to the Lead table:
  assigned_to, assigned_to_name, assigned_at, last_follow_up_at, follow_up_count

Also creates the Richard user (Cape Town rep) if not present.
Run against the live VPS DB.
"""
import sqlite3
import sys
import os
import hashlib

DB_PATH = os.environ.get("CRM_DB", "/root/rankbuilder/crm/data/rankbuilder_crm.db")


def hash_password(password: str) -> str:
    """Match the CRM's bcrypt hashing via passlib CryptContext."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Check current Lead columns
    c.execute("PRAGMA table_info(leads)")
    cols = [row[1] for row in c.fetchall()]
    print("Current Lead columns:", cols)

    # 2. Add new columns if missing
    new_cols = {
        "assigned_to": "VARCHAR(255)",
        "assigned_to_name": "VARCHAR(255)",
        "assigned_at": "DATETIME",
        "last_follow_up_at": "DATETIME",
        "follow_up_count": "INTEGER DEFAULT 0",
    }
    for col, ddl in new_cols.items():
        if col not in cols:
            c.execute(f"ALTER TABLE leads ADD COLUMN {col} {ddl}")
            print(f"Added column: {col} {ddl}")
        else:
            print(f"Column already exists: {col}")

    # 3. Create Richard user (Cape Town rep) if not present
    c.execute("SELECT id FROM users WHERE email='richard@houseofsupreme.co.za'")
    if c.fetchone():
        print("Richard user already exists")
    else:
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        client_id = None
        c.execute("SELECT id FROM clients LIMIT 1")
        row = c.fetchone()
        if row:
            client_id = row[0]
        hashed = hash_password("Richard1234!")
        c.execute(
            "INSERT INTO users (id, email, hashed_password, full_name, client_id, role, created_at, updated_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (str(uuid.uuid4()), "richard@houseofsupreme.co.za", hashed,
             "Richard", client_id, "CLIENT_ADMIN", now, now),
        )
        print("Created Richard user (Cape Town rep)")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
