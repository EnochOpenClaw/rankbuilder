# RankBuilder AI — HARO Responder

Automated HARO query monitoring, response drafting, and approval system.

## Quick Start

1. **Forward a HARO query** to `agentdevelopmentops@gmail.com`
2. **I draft a response** using `kimi-k2.6:cloud` and email it to you for review
3. **You reply YES** to approve, or EDIT with changes
4. **I send it** to the journalist from `craig@houseofsupreme.co.za`

## Architecture

```
HIMALAYA (agentdevelopmentops@gmail.com)
    ↓ cron every 30 min (7am–10pm SAST)
HARO MONITOR (haro_monitor.py)
    ↓ extracts query, checks relevance
RELEVANCE FILTER (haro_responder.py)
    - 24 target keywords (shutters, flyscreen, home improvement...)
    - 24 excluded keywords (crypto, travel, health...)
    ↓ if relevant
OLLAMA (kimi-k2.6:cloud)
    ↓ drafts response
BREVO SMTP → Craig for approval
    ↓ reply YES
BREVO SMTP → Journalist (reply+hash@helpareporter.com)
    + Blind BCC to Craig
```

## Scripts

- `scripts/haro_monitor.py` — Main scan + draft pipeline
- `scripts/haro_approve.py` — Manual approval helper / list pending
- `scripts/run_monitor.sh` — Cron runner wrapper
- `lib/haro_responder.py` — Core parsing, filtering, drafting logic
- `state/processed.jsonl` — State tracking (prevents double-processing)
- `logs/monitor.log` — Activity log

## Manual Commands

```bash
# Run monitor manually
python3 rankbuilder/scripts/haro_monitor.py

# List pending approvals
python3 rankbuilder/scripts/haro_approve.py

# Manually approve a specific email
python3 rankbuilder/scripts/haro_approve.py <email_id>

# Manually approve with edited text
python3 rankbuilder/scripts/haro_approve.py --approve <email_id> "edited response..."
```

## Key Config

- **Model:** `kimi-k2.6:cloud` via local Ollama (fast, cloud-routed)
- **Email:** Brevo SMTP (`smtp-relay.brevo.com:587`)
- **Sender:** `craig@houseofsupreme.co.za`
- **Approval inbox:** Craig replies YES to the approval email
- **Blind CC:** Craig gets BCC of every sent response

## HARO + Connectively Setup

**HARO Profile:** helpareporter.com/journalist/craig-pauls ✅
**Connectively:** connected to same profile — keyword alerts active ✅
**Login:** support@ct-designs.co.za (same as HARO)

### Connectively Keyword Alerts
- `shutters` — custom aluminum/wood shutters, security shutters, roller shutters
- `home improvement` — renovation, window replacement, home upgrades
- `fly screen` — flyscreen doors/windows, insect protection

### Connectively Expertise Bio
Custom aluminum shutters and flyscreen solutions for South African homes, window security and home safety products, home improvement and renovation expertise, fly and insect protection systems, residential window and door installations, South African home security industry trends

### Additional Alerts to Consider (optional)
- `window security` — home security, window locks, security shutters
- `aluminum doors` OR `aluminum windows` — specific product queries
- `home safety` — safety hardware, door hardware

## Keyword Filtering

**Target (relevant if 1+ match):**
- shutters, fly screen, flyscreen, window screens, door screens, aluminum doors, aluminum windows, home improvement, home renovation, window replacement, home security, home safety, home comfort, ventilation, pest control, insect protection, roller shutters, security shutters, window coverings, door coverings, balcony screens, patio enclosures, sun control, privacy solutions
shutters, fly screen, flyscreen, window screens, door screens, aluminum doors, aluminum windows, home improvement, home renovation, window replacement, home security, home safety, home comfort, ventilation, pest control, insect protection, roller shutters, security shutters, window coverings, door coverings, balcony screens, patio enclosures, sun control, privacy solutions

**Excluded (always skip):**
crypto, bitcoin, blockchain, flight, airline, travel agent, ornithologist, bird, chef, louisiana, bookshop, coffee shop, barista, sex life, interview, podcast, chicken, recipe, FDA, oncologist, vitamin, dermatologist, anti-aging, mental health

## Cron Schedule

- HARO Monitor: every 30 min, 7am–10pm SAST (cron ID: `5dc88ca2-34bb-4433-b755-0d08e9fed3ab`)
- Daily HOS Backup: 4pm SAST
- Morning Briefing: 7am SAST
- Maintenance: midnight SAST

## For When Craig Has HARO Queries

When a relevant HARO query arrives and gets drafted:

1. Craig receives approval email at `craig@houseofsupreme.co.za`
2. Subject: `📋 [HARO APPROVAL] {Outlet} — "Query summary..."`
3. Craig replies:
   - `YES` → response sent to journalist
   - `SKIP` → response discarded
   - `EDIT {revised text}` → send edited version
