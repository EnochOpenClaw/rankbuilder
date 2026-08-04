#!/usr/bin/env python3
"""Seed the CRM database on VPS with all required tables + HOS data."""
import sqlite3, uuid, os
from datetime import datetime

DB_PATH = '/root/rankbuilder/crm/data/rankbuilder_crm.db'
os.makedirs("/root/rankbuilder/crm/data", exist_ok=True))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

now = datetime.utcnow().isoformat()
hos_id = 'e74119b9-17e3-4f74-b218-67ef0e66f1cc'
api_key = os.environ.get('HOS_CLIENT_API_KEY', '')

# Tables
for sql in [
    """CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY, company_name TEXT NOT NULL,
        contact_email TEXT NOT NULL, notification_channel TEXT DEFAULT 'EMAIL',
        notification_target TEXT NOT NULL, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY, client_id TEXT, name TEXT NOT NULL,
        channel TEXT, status TEXT DEFAULT 'ACTIVE', started_at TEXT, ended_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY, client_id TEXT, campaign_id TEXT,
        source TEXT NOT NULL, source_query TEXT, source_detail TEXT,
        utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, location TEXT,
        status TEXT DEFAULT 'NEW', lead_type TEXT, quality_score INTEGER,
        contact_name TEXT, contact_email TEXT, contact_phone TEXT,
        company_name TEXT, company_website TEXT, message_excerpt TEXT,
        pitch_sent TEXT, sent_to_client_at TEXT, client_response TEXT,
        conversion_status TEXT, converted_at TEXT, notes TEXT,
        created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS lead_history (
        id TEXT PRIMARY KEY, lead_id TEXT, field_changed TEXT NOT NULL,
        old_value TEXT, new_value TEXT, changed_at TEXT, changed_by TEXT)""",
    """CREATE TABLE IF NOT EXISTS notification_settings (
        id TEXT PRIMARY KEY, client_id TEXT, notification_type TEXT NOT NULL,
        target TEXT, name TEXT, enabled INTEGER DEFAULT 1, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL,
        full_name TEXT NOT NULL, client_id TEXT, role TEXT NOT NULL DEFAULT 'VIEWER',
        created_at TEXT, updated_at TEXT, is_active INTEGER DEFAULT 1)""",
]:
    cur.execute(sql)

# Add missing columns to existing tables
for table, col, dtype in [
    ('clients', 'api_key', 'TEXT'),
    ('clients', 'notification_channel', "TEXT DEFAULT 'EMAIL'"),
    ('leads', 'source_detail', 'TEXT'),
    ('leads', 'utm_source', 'TEXT'),
    ('leads', 'utm_medium', 'TEXT'),
    ('leads', 'utm_campaign', 'TEXT'),
    ('leads', 'location', 'TEXT'),
]:
    try:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {dtype}')
        print(f'  + {table}.{col}')
    except Exception as e:
        print(f'  ~ {table}.{col}: {e}')

# HOS client
cur.execute("""INSERT OR IGNORE INTO clients
    (id, api_key, company_name, contact_email, notification_channel, notification_target, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    [hos_id, api_key, 'House of Supreme', 'craig@houseofsupreme.co.za', 'EMAIL', 'craigp@ct-designs.co.za', now, now])

# Notification recipients
for email, name in [
    ('tiaan@houseofsupreme.co.za', 'Tiaan'),
    ('robin@houseofsupreme.co.za', 'Robin'),
    ('craigp@ct-designs.co.za', 'Craig'),
]:
    nid = str(uuid.uuid4())
    cur.execute("""INSERT OR IGNORE INTO notification_settings
        (id, client_id, notification_type, target, name, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [nid, hos_id, 'EMAIL', email, name, 1, now])

conn.commit()

# Show what we have
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)
print('Clients:', cur.execute('SELECT id, company_name, api_key FROM clients').fetchall())
print('Notification settings:', cur.execute('SELECT id, target, name FROM notification_settings').fetchall())
print('DONE')
