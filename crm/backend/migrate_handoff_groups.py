"""
RankBuilder CRM — Partner Handoff Group Migration
==================================================
Creates the NEW "Partner Handoff Managers" user group and enrols tiaan in it.

Background (Craig 2026-09-14):
  - Tiaan is SALES_MANAGER and already has the delegated handoff CAPABILITY
    (POST /api/leads/{id}/handoff allows SYSTEM_ADMIN / CLIENT_ADMIN /
    SALES_MANAGER). What he lacks is the CLIENT/CONTACT VISIBILITY to actually
    pick a partner client + target user for handoff — the "Clients" section keeps
    hiding partner clients, and the target-user list is scoped to his own client.
  - Craig's direction: "Separate them so we can leave the existing as they are
    but just create a new user group." So instead of re-scoping any existing role,
    we introduce a NEW user-group concept that GRANTS additive read visibility of
    partner clients + their contacts for handoff, WITHOUT touching role semantics.
  - Only tiaan is enrolled. clints/contacts of other users (richard / robin /
    lee-ann / vanessa / irene / freedom / sian) are unaffected; no role changes.

What this script does (idempotent, safe):
  1. Create the handoff_groups + user_handoff_groups tables if missing
     (mirrors the additive SQLite migrations the app runs on startup).
  2. Ensure the named group "Partner Handoff Managers" exists.
  3. Enrol tiaan@houseofsupreme.co.za into that group.
  It touches ONLY group membership — never roles.

Dry-run by default; apply with --apply.

Run on VPS:  python3 /root/rankbuilder/crm/backend/migrate_handoff_groups.py --apply
             (local: python3 backend/migrate_handoff_groups.py --apply)
             (CRM_DB env var overrides the DB path if needed)
"""

import os
import sys
import uuid
import argparse
import sqlite3

DB_PATH = os.environ.get("CRM_DB", "/root/rankbuilder/crm/data/rankbuilder_crm.db")

GROUP_NAME = "Partner Handoff Managers"
GROUP_DESC = ("Cross-client READ visibility of partner clients + their contacts "
              "for handoff targeting (additive; does not change role semantics).")

# Members to enrol into the group. Tiaan was the original member; Craig added
# robin + vanessa (2026-09-15) so they can also switch clients in the top bar.
# Roles are untouched — membership is purely additive.
ENROLL = [
    "tiaan@houseofsupreme.co.za",
    "robin@houseofsupreme.co.za",
    "vanessa@houseofsupreme.co.za",
]


def _ensure_tables(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS handoff_groups (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description VARCHAR(255),
            created_at DATETIME
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_handoff_groups (
            user_id VARCHAR(36) NOT NULL,
            group_id VARCHAR(36) NOT NULL,
            PRIMARY KEY (user_id, group_id)
        )
    """)


def migrate(db_path, apply: bool):
    if not os.path.exists(db_path):
        print("❌ DB not found at %s. Set CRM_DB env var if different." % db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # ── 1. Ensure tables exist ─────────────────────────────────────────────
    _ensure_tables(c)
    print("ℹ️  handoff_groups / user_handoff_groups tables ensured.")

    # ── 2. Ensure the named group exists ───────────────────────────────────
    row = c.execute("SELECT id, name, description FROM handoff_groups WHERE name=?",
                    (GROUP_NAME,)).fetchone()
    if row:
        gid = row[0]
        print(f"✅ Handoff group exists: '{GROUP_NAME}' (id={gid[:8]}...)")
    else:
        gid = str(uuid.uuid4())
        print(f"ℹ️  Group '{GROUP_NAME}' not found — will create it.")
        if apply:
            c.execute(
                "INSERT INTO handoff_groups (id, name, description, created_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (gid, GROUP_NAME, GROUP_DESC),
            )
            conn.commit()
            print(f"✅ Created group '{GROUP_NAME}' (id={gid[:8]}...).")
        else:
            print("   (dry-run) Run with --apply to create it.")

    # ── 3. Enrol members ───────────────────────────────────────────────────
    print("\n── Handoff group membership (dry-run: --apply to change) ──")
    for email in ENROLL:
        u = c.execute("SELECT id, role FROM users WHERE email=?", (email,)).fetchone()
        if not u:
            print(f"  ⚠️  user not found: {email}")
            continue
        uid, role = u[0], u[1]
        member = c.execute(
            "SELECT 1 FROM user_handoff_groups WHERE user_id=? AND group_id=?",
            (uid, gid),
        ).fetchone()
        status = "already a member" if member else "→ will enrol"
        print(f"  {email:<35} (role={role:<15}) {status}")
        if apply and not member:
            c.execute(
                "INSERT INTO user_handoff_groups (user_id, group_id) VALUES (?, ?)",
                (uid, gid),
            )
            conn.commit()
            print(f"  ✅ Enrolled {email} into '{GROUP_NAME}'.")

    # ── 4. Show full group roster (no changes) ─────────────────────────────
    print("\n── Current roster for '{GROUP_NAME}' ──")
    rows = c.execute(
        "SELECT u.email, hg.name FROM user_handoff_groups ugh "
        "JOIN users u ON u.id = ugh.user_id "
        "JOIN handoff_groups hg ON hg.id = ugh.group_id "
        "WHERE hg.name=?", (GROUP_NAME,)
    ).fetchall()
    if rows:
        for email, gname in rows:
            print(f"  • {email}  [{gname}]")
    else:
        print("  (no members yet)")

    conn.close()
    print("\n✅ Done. Roles are untouched — this migration only manages group membership.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CRM partner handoff group migration")
    parser.add_argument("--apply", action="store_true",
                        help="Create group + enrol members. Default: dry-run only.")
    parser.add_argument("--db", default=None, help="Override DB path (or set CRM_DB env)")
    args = parser.parse_args()
    migrate(args.db or DB_PATH, args.apply)
