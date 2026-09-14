"""
RankBuilder CRM — Role & Delegation Migration
=============================================
Adds the SALES_MANAGER role and widens the users.role column so new roles fit.

Background (Craig 2026-09-14):
  - Handing a lead off to Cape Town (POST /api/leads/{id}/handoff) was SYSTEM_ADMIN
    only. It is now allowed for SYSTEM_ADMIN, CLIENT_ADMIN and SALES_MANAGER so the
    capability can be delegated without Craig.
  - A new SALES_MANAGER role exists for regional sales leads: they can view their
    own client's leads, log follow-ups, reassign leads within their client, hand
    leads off to partner/Cape Town clients, and manage their client's notification
    groups. It is NOT granted user-account administration (SYSTEM_ADMIN/CLIENT_ADMIN
    only) nor cross-client access.

What this script does (idempotent, safe):
  1. Widen users.role from VARCHAR(12) -> VARCHAR(20) (advisory in SQLite, but keeps
     DDL accurate and future-proof). SQLite already stores SALES_MANAGER fine, so
     this is belt-and-braces, not strictly required.
  2. Reassign existing users to the FINAL least-privilege roles (Craig confirmed
     2026-09-14): tiaan -> SALES_MANAGER; craig stays SYSTEM_ADMIN; lee-ann/robin/
     vanessa -> VIEWER; agent -> AGENT. richard is DELIBERATELY left untouched.
  3. Replace the stale Craig notification email `craigp@ct-designs.co.za` with
     `craig@houseofsupreme.co.za` everywhere it appears (notification_settings).
     Dry-run by default; apply with --apply.

Run on VPS:  python3 /root/rankbuilder/crm/backend/migrate_roles.py --apply
             (local: python3 backend/migrate_roles.py --apply)
             (CRM_DB env var overrides the DB path if needed)

The role + email changes below are NOT applied unless you pass --apply.
Review the table first with --dry-run (the default).
"""

import os
import sys
import argparse
import sqlite3

DB_PATH = os.environ.get("CRM_DB", "/root/rankbuilder/crm/data/rankbuilder_crm.db")

# ── Role layout (Craig 2026-09-14 FINAL) ────────────────────────────────────
# email -> role. Only roles in the UserRole enum are valid:
#   SYSTEM_ADMIN, CLIENT_ADMIN, SALES_MANAGER, AGENT, VIEWER
# - craig:  SYSTEM_ADMIN  (full, cross-client admin — unchanged)
# - tiaan:  SALES_MANAGER  (JHB rep — given hand-off capability so HE can use the
#                           "Hand to partner" section and assign Cape Town jobs himself)
# - richard: DO NOT TOUCH — Craig confirmed Richard's current setup is perfect
#            (Cape Town rep, sees only CPT-assigned jobs, manages them). He is NOT
#            in this map and is never reassigned or re-scoped by this migration.
# - robin, lee-ann, vanessa: PENDING CRAIG CONFIRMATION — they are CLIENT_ADMIN on
#            production; demoting them to VIEWER would remove their write access on
#            the live system, which Craig has not explicitly approved. Excluded from
#            this migration (left untouched) until he rules on it.
# - agent@rankbuilder.local: AGENT (only their own assigned leads)
DEFAULT_ROLE_MAP = {
    "craig@houseofsupreme.co.za": "SYSTEM_ADMIN",
    "tiaan@houseofsupreme.co.za": "SALES_MANAGER",
    "agent@rankbuilder.local": "AGENT",
}
# Users deliberately EXCLUDED from reassignment (never touched):
#   richard@houseofsupreme.co.za — Craig's final call: leave exactly as he is now.
#   robin@ / lee-ann@ / vanessa@houseofsupreme.co.za — pending Craig's confirmation
#   on demoting them from CLIENT_ADMIN to VIEWER on the live system.


def _column_count(c, table):
    c.execute("PRAGMA table_info(%s)" % table)
    return len(c.fetchall())


def migrate(db_path, apply: bool):
    if not os.path.exists(db_path):
        print("❌ DB not found at %s. Set CRM_DB env var if different." % db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # ── 1. Widen users.role to VARCHAR(20) ─────────────────────────────────
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = c.fetchone()
    if row:
        sql = row[0]
        # SQLite column widths are advisory; rebuild the table so the DDL reads
        # VARCHAR(20). If already widened, skip.
        if "role" in sql and "VARCHAR(20)" not in sql:
            print("ℹ️  users.role currently: VARCHAR(12) — will widen to VARCHAR(20).")
            if apply:
                _widen_role_column(conn, c)
                print("✅ users.role widened to VARCHAR(20).")
            else:
                print("   (dry-run) Run with --apply to widen.")
        else:
            print("ℹ️  users.role already widened (or no change needed).")
    else:
        print("ℹ️  users table not found — nothing to widen (fresh DB will be created by the app).")

    # ── 2. Role reassignment (only with --apply) ───────────────────────────
    print("\n── Recommended role layout (least privilege) ──")
    for email, role in DEFAULT_ROLE_MAP.items():
        c.execute("SELECT role FROM users WHERE email=?", (email,))
        cur = c.fetchone()
        current = cur[0] if cur else "—not found—"
        marker = "→" if cur and cur[0] != role else "(unchanged)" 
        print(f"  {email:<35} {current:<20} {marker} {role}")
    if apply:
        for email, role in DEFAULT_ROLE_MAP.items():
            cur = c.execute("SELECT role FROM users WHERE email=?", (email,)).fetchone()
            if cur and cur[0] != role:
                c.execute("UPDATE users SET role=? WHERE email=?", (role, email))
                print(f"  ✅ {email} -> {role}")
        conn.commit()
        print("\n✅ Role reassignment applied.")
    else:
        print("\n(dry-run) Role reassignment NOT applied. Pass --apply to change roles.")
        print("Confirm the layout with Craig first — reassignment can affect access.")

    # ── 3. Swap stale Craig recipient email (Craig confirmed 2026-09-14) ──────
    # notification_settings row ns-hos-craig (and any other row) used the old/wrong
    # farcaster email craigp@ct-designs.co.za. Replace with the correct one so
    # Craig still gets new-lead / SLA / follow-up alerts.
    STALE_EMAIL = "craigp@ct-designs.co.za"
    GOOD_EMAIL = "craig@houseofsupreme.co.za"
    stale_rows = c.execute(
        "SELECT id, target FROM notification_settings WHERE target=?", (STALE_EMAIL,)
    ).fetchall()
    if stale_rows:
        print("\n── Stale Craig recipient email ──")
        for rid, target in stale_rows:
            print(f"  {rid} : {target}  ->  {GOOD_EMAIL}")
        if apply:
            c.execute("UPDATE notification_settings SET target=? WHERE target=?",
                      (GOOD_EMAIL, STALE_EMAIL))
            conn.commit()
            print("✅ Stale Craig email swapped to " + GOOD_EMAIL)
        else:
            print("   (dry-run) Run with --apply to swap.")
    else:
        print("ℹ️  No notification_settings rows use the stale Craig email.")

    conn.close()


def _widen_role_column(conn, c):
    """Rebuild users with role VARCHAR(20) via the standard 9-step SQLite resize."""
    table = "users"
    cols_sql = c.execute("PRAGMA table_info(%s)" % table).fetchall()
    col_names = [r[1] for r in cols_sql]
    col_defs = ", ".join(
        '"%s" %s%s%s' % (
            r[1], r[2],
            " NOT NULL" if r[3] else "",
            (" DEFAULT %s" % r[4]) if r[4] is not None else "",
        )
        for r in cols_sql
    )
    # Role column specifically -> VARCHAR(20)
    col_defs = col_defs.replace('"role" VARCHAR(12)', '"role" VARCHAR(20)')
    col_list = ", ".join('"%s"' % n for n in col_names)

    c.execute('ALTER TABLE users RENAME TO users_old')
    c.execute('CREATE TABLE users (%s)' % col_defs)
    c.execute('INSERT INTO users (%s) SELECT %s FROM users_old' % (col_list, col_list))
    c.execute('DROP TABLE users_old')
    conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CRM role & delegation migration")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (widening + role reassignment). Default: dry-run only.")
    parser.add_argument("--db", default=None, help="Override DB path (or set CRM_DB env)")
    args = parser.parse_args()
    migrate(args.db or DB_PATH, args.apply)
