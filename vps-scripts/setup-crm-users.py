#!/usr/bin/env python3
"""Set API key on existing HOS client + create users with hashed passwords."""
import sqlite3, os
from datetime import datetime

DB_PATH = '/root/rankbuilder/crm/data/rankbuilder_crm.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

now = datetime.utcnow().isoformat()
hos_id = 'e74119b9-17e3-4f74-b218-67ef0e66f1cc'

# Set API key
cur.execute('UPDATE clients SET api_key = ? WHERE id = ?',
    (os.environ.get('HOS_CLIENT_API_KEY', ''), hos_id))
print('API key set:', cur.rowcount, 'row(s) updated')

# Create users with bcrypt-hashed passwords
import bcrypt
def hashpw(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

users = [
    ('craig@houseofsupreme.co.za', 'RankBuilder!23', 'Craig Pauls',    hos_id, 'SYSTEM_ADMIN'),
    ('tiaan@houseofsupreme.co.za',  'Tiaan1234!',   'Tiaan van der Walt', hos_id, 'CLIENT_ADMIN'),
    ('robin@houseofsupreme.co.za',  'Robin1234!',   'Robin Bras',          hos_id, 'VIEWER'),
]

for email, pw, name, cid, role in users:
    existing = cur.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    hp = hashpw(pw)
    if existing:
        cur.execute('UPDATE users SET hashed_password=?, full_name=?, client_id=?, role=? WHERE email=?',
            (hp, name, cid, role, email))
        print(f'  Updated: {email}')
    else:
        import uuid
        uid = str(uuid.uuid4())
        cur.execute("""INSERT INTO users (id,email,hashed_password,full_name,client_id,role,created_at,updated_at,is_active)
            VALUES (?,?,?,?,?,?,?,?,1)""",
            (uid, email, hp, name, cid, role, now, now))
        print(f'  Created: {email}')

conn.commit()
print('\nClients:', cur.execute('SELECT id, company_name, api_key FROM clients').fetchall())
print('Users:', cur.execute('SELECT id, email, full_name, role FROM users').fetchall())
print('DONE')
