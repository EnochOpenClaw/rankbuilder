# RankBuilder CRM

Autonomous SEO lead generation CRM — Phase 1.

## Quick Start

```bash
# 1. Start the backend
cd backend
pip install -r ../requirements.txt --break-system-packages
uvicorn backend.app:app --host 0.0.0.0 --port 8000

# 2. Seed HOS as the first client (in another terminal)
python3 -m backend.seed

# 3. Start the frontend
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173  
Backend API: http://localhost:8000  
API docs: http://localhost:8000/docs

## Tech Stack

- **Backend:** Python/FastAPI + SQLAlchemy + SQLite
- **Frontend:** React 19 + Vite + AntD
- **Database:** SQLite (`data/rankbuilder_crm.db`)

## What's Built (Phase 1)

- Lead capture API (`POST /api/leads`) — agents write here
- Lead list/detail/update/delete API
- Full audit trail (LeadHistory)
- Dashboard: lead counts, qualification rate, source breakdown
- HOS client portal with lead list, filters, detail drawer, status updates

## API Basics

```bash
# Create a lead
curl -X POST http://localhost:8000/api/leads \
  -H 'Content-Type: application/json' \
  -d '{
    "client_id": "<your-client-id>",
    "source": "HARO",
    "source_query": "aluminum shutters south africa",
    "contact_name": "John Smith",
    "contact_email": "john@example.com",
    "company_name": "Smith Renovations",
    "message_excerpt": "Looking for aluminium shutter installation",
    "quality_score": 4
  }'

# List leads
curl "http://localhost:8000/api/leads?client_id=<id>&limit=20"

# Update lead
curl -X PATCH "http://localhost:8000/api/leads/<lead-id>" \
  -H 'Content-Type: application/json' \
  -d '{"status": "QUALIFIED", "lead_type": "VALID"}'
```

## Adding to Systemd (WSL2)

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/rankbuilder-crm.service << 'EOF'
[Unit]
Description=RankBuilder CRM Backend
After=network.target

[Service]
WorkingDirectory=/home/enoch/.openclaw/workspace/rankbuilder/crm
ExecStart=/usr/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now rankbuilder-crm
```
