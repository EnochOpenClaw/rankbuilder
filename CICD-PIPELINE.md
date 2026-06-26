# RankBuilder CI/CD Pipeline — Option B Architecture

**Philosophy:** Stable infrastructure first. Build once, deploy with confidence.

---

## Architecture Overview

```
Local (WSL2)                    GitHub                     VPS (Contabo)
─────────────                   ──────                     ───────────
Dev & test  ──────────────────►  Push  ──────────────────►  Coolify
  - Edit scripts                 main branch                   pulls & builds
  - Run locally                  triggers deploy               deploys container
  - git push when stable                                      runs 24/7
```

**Key principle:** The VPS container runs the show. Local is for development and testing only.

---

## Repository Structure

```
rankbuilder/
├── Dockerfile                  # Container image
├── docker-compose.yml          # Local dev + production override
├── Dockerfile.healthcheck      # Lightweight health check runner
├── .dockerignore
├── .env.example                # All env vars documented
├── scripts/
│   ├── haro_monitor.py         # Cron: every 30 min
│   ├── connectively_monitor.py # Cron: every 30 min
│   ├── guest_outreach_engine.py# Cron: daily
│   ├── prospect_checker.py     # Cron: every 3 days
│   └── run_monitor.sh          # Wrapper that runs correct script by env var
├── lib/                        # Shared modules
├── state/                      # Persistent state (gitignored, volume-mounted)
│   ├── drafts/
│   ├── processed.jsonl
│   └── ...
├── prospects/                  # Prospect database (gitignored, volume-mounted)
└── rankings/                   # Ranking data (gitignored, volume-mounted)
```

---

## Container Design

### Base Image
`python:3.11-slim` — small, stable, well-maintained

### Entrypoint
Custom Python runner that:
1. Reads `RUN_MODE` env var to determine what to run
2. Starts cron daemon in background
3. Runs appropriate script on schedule
4. Exposes health check on port 8080

### RUN_MODE options
| Mode | What it does |
|------|-------------|
| `cron` | Start cron daemon + all scheduled scripts (production) |
| `haro` | Run haro_monitor.py once and exit |
| `connectively` | Run connectively_monitor.py once and exit |
| `guest` | Run guest_outreach_engine.py once and exit |
| `health` | Run health check and exit (for liveness probe) |

### Cron Schedule (inside container)
```
*/30 7-22 * * *  /app/run_mode.sh haro
*/30 7-22 * * *  /app/run_mode.sh connectively
0 8,12,18 * * *  /app/run_mode.sh guest
0 0 */3 * *      /app/run_mode.sh prospect
```

### State Persistence
- `state/`, `prospects/`, `rankings/` → named Docker volume
- Mounted at `/app/data` inside container
- Survives container restarts/rebuilds

---

## Environment Variables (Secrets)

Set in **Coolify UI** (not in code):

| Variable | Description |
|----------|-------------|
| `BREVO_API_KEY` | Brevo SMTP/API key |
| `BREVO_ENDPOINT` | https://api.brevo.com/v3/smtp/email |
| `SENDER_EMAIL` | ai@fortressblinds.co.za |
| `SENDER_NAME` | FortressBlinds AI |
| `NOTIFY_EMAIL` | craig@fortressblinds.co.za |
| `HARO_EMAIL` | agentdevelopmentops@gmail.com |
| `HARO_PASSWORD` | (app password) |
| `CONNECTIVELY_EMAIL` | agentdevelopmentops@gmail.com |
| `CONNECTIVELY_PASSWORD` | (app password) |
| `GUEST_SMTP_HOST` | smtp-relay.brevo.com |
| `GUEST_SMTP_PORT` | 587 |
| `GUEST_SMTP_USER` | ac9618001@smtp-brevo.com |
| `GUEST_SMTP_PASS` | bskxwxpaf7akXff |
| `GITHUB_TOKEN` | GitHub PAT for git ops |
| `RUN_MODE` | `cron` (production) |
| `HEALTHCHECK_URL` | (optional, for uptime monitoring) |

---

## Coolify Deployment Config

**Project:** `rankbuilder`  
**GitHub repo:** `EnochOpenClaw/rankbuilder`  
**Branch:** `main`  
**Build pack:** Dockerfile  
**Port:** 8080 (health only, no public HTTP)  
**Volume:** `rankbuilder-data` → `/app/data`

### Startup Command
```bash
RUN_MODE=cron
```

### Health Check
```
GET http://localhost:8080/health
Expected: 200 + {"status":"ok"}
Interval: 60s
Timeout: 10s
Restart threshold: 3
```

---

## Git Workflow

### Branch Strategy
- `main` → production (auto-deploys via Coolify)
- `develop` → staging/testing (manual deploy)
- Feature branches → PR to develop

### Commit Rules
- **Never commit secrets** — only `.env.example`
- **Never commit state/** — in `.gitignore`
- **Test locally before push** — especially for haro/connectively changes

### Push Checklist
Before pushing to `main`:
- [ ] Tested modified script locally
- [ ] No secrets in diff
- [ ] State dirs not in diff
- [ ] Dockerfile still builds
- [ ] docker-compose still works

### Local Dev Cycle
```bash
# Edit scripts locally
cd rankbuilder
docker-compose up --build   # Build + run in foreground
docker-compose exec rankbuilder python scripts/haro_monitor.py  # Test single script
docker-compose down        # Stop
git add . && git commit -m "description" && git push  # Deploy
```

---

## Deployment Flow

### Normal deployment (git push)
```
local: git push origin main
  → GitHub receives push
  → (Optional: GitHub Actions CI runs tests)
  → Coolify webhook triggered
  → Coolify pulls latest main
  → Docker build (cached layers)
  → Docker deploy (zero-downtime rolling)
  → Container starts with new image
  → Previous container stops
```

### Manual deploy (Coolify UI)
- Click "Redeploy" on Coolify dashboard
- Select commit or use latest

### Rollback
- Coolify keeps previous image
- Click "Previous deployment" → "Redeploy"

---

## Local Development Setup

### Prerequisites
```bash
# Install once
docker --version
docker-compose --version   # or: docker compose plugin
```

### Start local dev
```bash
cd rankbuilder
cp .env.example .env
# Fill in .env with real values
docker-compose up --build
```

### Run specific script locally
```bash
docker-compose exec rankbuilder python scripts/haro_monitor.py
docker-compose exec rankbuilder python scripts/connectively_monitor.py
```

### View logs
```bash
docker-compose logs -f rankbuilder
docker-compose logs -f rankbuilder --tail=100
```

### Stop
```bash
docker-compose down
```

---

## Health Check

Container exposes `GET /health` on port 8080:

```python
@app.route("/health")
def health():
    return {"status": "ok", "version": VERSION, "uptime": uptime()}
```

Used by:
- Coolify liveness probe
- Uptime monitoring (optional)
- `docker ps` shows healthy/unhealthy

---

## File: Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY scripts/ requirements.txt* ./

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null \
    || pip install --no-cache-dir \
        requests \
        beautifulsoup4 \
        lxml \
        playwright \
        python-dotenv \
        schedule

# Copy application
COPY . .

# Health check server
COPY docker-healthcheck.py /app/healthcheck.py

# Volume mount point
VOLUME ["/app/data"]

# Expose health port
EXPOSE 8080

# Entrypoint
ENTRYPOINT ["python", "docker-healthcheck.py"]
```

---

## File: docker-compose.yml

```yaml
version: "3.8"

services:
  rankbuilder:
    build: .
    container_name: rankbuilder
    restart: unless-stopped
    environment:
      - RUN_MODE=cron
    env_file:
      - .env
    volumes:
      - rankbuilder-data:/app/data
    healthcheck:
      test: ["CMD", "python", "healthcheck.py"]
      interval: 60s
      timeout: 10s
      retries: 3

volumes:
  rankbuilder-data:
    driver: local
```

---

## File: docker-healthcheck.py

Simple health + cron runner:

```python
#!/usr/bin/env python3
"""Docker entrypoint: health check server + cron runner"""

import os
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

HEALTH_PORT = 8080
START = time.time()

def run_cron():
    """Run cron daemon and scheduled jobs."""
    # Write crontab
    with open("/etc/crontab", "w") as f:
        f.write(f"""\
# m h dom mon dow user  command
*/30 7-22 * * * root /app/run_mode.sh haro >> /app/data/logs/haro.log 2>&1
*/30 7-22 * * * root /app/run_mode.sh connectively >> /app/data/logs/connectively.log 2>&1
0 8,12,18 * * * root /app/run_mode.sh guest >> /app/data/logs/guest.log 2>&1
0 0 */3 * * root /app/run_mode.sh prospect >> /app/data/logs/prospect.log 2>&1
""")
    subprocess.run(["cron"], check=False)
    # Keep alive
    while True:
        time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args): pass  # Silent

if __name__ == "__main__":
    t = threading.Thread(target=run_cron, daemon=True)
    t.start()
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), Handler)
    print(f"Health check server running on :{HEALTH_PORT}")
    server.serve_forever()
```

---

## File: run_mode.sh

```bash
#!/bin/bash
# Maps RUN_MODE env var to script execution
MODE="${1:-${RUN_MODE:-cron}}"
cd /app

case "$MODE" in
  haro)          python scripts/haro_monitor.py ;;
  connectively)  python scripts/connectively_monitor.py ;;
  guest)         python scripts/guest_outreach_engine.py ;;
  prospect)      python scripts/prospect_checker.py ;;
  health)        python -c "print('ok')" ;;
  *)             echo "Unknown mode: $MODE" ;;
esac
```

---

## Secrets Management

| Secret | Storage | Retrieval |
|--------|---------|-----------|
| API keys | Coolify UI → project env vars | Injected as env vars at container start |
| Brevo credentials | Coolify UI | `os.environ["BREVO_API_KEY"]` |
| HARO/Connectively creds | Coolify UI | `os.environ["HARO_EMAIL"]` |
| GitHub PAT | Coolify UI | Used by git operations |

**Never do:**
- Commit `.env` files to git
- Put real keys in code
- Use the same key in both local dev and production without isolation

---

## What's Working Now vs What We're Building

| Component | Now | After CI/CD |
|-----------|-----|-------------|
| HARO monitor | Local cron on WSL | VPS container, 24/7 |
| Connectively | Local cron on WSL | VPS container, 24/7 |
| Guest outreach | Local | VPS container, 24/7 |
| Deploy | Manual file copy | `git push` → auto deploy |
| Rollback | Re-copy files | One-click in Coolify |
| Logs | Scattered | Centralised in `/app/data/logs/` |
| Secrets | In `.env` locally | In Coolify UI |
| Testing | Blind push | Local docker-compose first |
| Branching | None | `develop` → `main` workflow |
