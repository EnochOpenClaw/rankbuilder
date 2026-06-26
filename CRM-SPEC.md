# RankBuilder CRM — SPEC.md

## Concept

**RankBuilder AI** is a standalone company providing autonomous SEO lead generation as a service.
- **Anchor tenant:** House of Supreme (HOS) — proof of concept, first reference client
- **Proof of value:** Valid leads delivered (real potential customers, not job seekers, not irrelevant)
- **Strategy:** Build once, license to multiple companies via associate network referrals

A simple CRM designed around what RankBuilder actually needs to do: capture leads, qualify them, route them, track their status, and prove ROI.

---

## What the CRM Needs to Do

### 1. Lead Capture
- Receive leads from multiple channels: HARO responses, Connectively pitches, guest outreach, web search discovery
- Store lead data: name, company, website, email, phone (when available), source channel, timestamp
- Capture lead context: what query they submitted, what response/pitch was sent, what outcome

### 2. Lead Qualification
- Classify leads by type: **VALID** (potential customer), **INVALID** (job seeker, competitor, irrelevant), **FOLLOW_UP** (warm but not ready)
- Quality score: 1-5 based on relevance, authority, intent signals
- Source attribution: which RankBuilder campaign/channel produced this lead

### 3. Lead Status Pipeline
```
NEW → REVIEWED → QUALIFIED → SENT_TO_CLIENT → CONTACTED → CONVERTED/LOST
```
- Every transition logged with timestamp
- Assigned owner per lead (automated agent or human)

### 4. Client Portal (HOS)
- HOS sees their leads only
- Dashboard: total leads, qualified rate, conversion rate, source breakdown
- Lead detail view with full history
- Email/SMS notification when new qualified lead arrives
- Simple lead status update (contacted, converted, lost)

### 5. Proof & Reporting
- Lead volume over time (daily/weekly/monthly)
- Qualification rate by channel (HARO vs Connectively vs Guest Outreach)
- Conversion rate (leads → HOS customers)
- Average response time (lead captured → delivered to client)
- Exportable lead reports

### 6. Multi-Client Readiness
- Architecture supports multiple client accounts
- Each client: isolated lead pool, dashboard, notifications
- RankBuilder ops team: cross-client view, all leads, all campaigns
- White-label ready (client-facing domain/brand)

---

## Data Model

### Lead
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| client_id | uuid | HOS = first client |
| source | enum | HARO, CONNECTIVELY, GUEST_OUTREACH, WEB_SEARCH, MANUAL |
| source_query | string | e.g. "aluminum shutters south africa" |
| status | enum | NEW, REVIEWED, QUALIFIED, SENT, CONTACTED, CONVERTED, LOST |
| quality_score | int | 1-5 |
| lead_type | enum | VALID, INVALID, FOLLOW_UP |
| contact_name | string | |
| contact_email | string | |
| contact_phone | string | optional |
| company_name | string | |
| company_website | string | |
| message_excerpt | text | what the lead said / context |
| pitch_sent | text | what RankBuilder sent |
| sent_to_client_at | datetime | |
| client_response | text | HOS feedback on lead |
| conversion_status | enum | null, CONVERTED, LOST |
| converted_at | datetime | |
| notes | text | internal |
| created_at | datetime | |
| updated_at | datetime | |

### Client
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| company_name | string | |
| contact_email | string | |
| notification_channel | enum | EMAIL, SMS, WEBHOOK |
| notification_target | string | email address or webhook URL |
| created_at | datetime | |

### Campaign
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| client_id | uuid | |
| name | string | e.g. "HOS-Q3-HARO-Outreach" |
| channel | enum | HARO, CONNECTIVELY, GUEST_OUTREACH |
| status | enum | ACTIVE, PAUSED, COMPLETED |
| started_at | datetime | |
| ended_at | datetime | |

---

## Tech Stack

- **Database:** SQLite (single-file, simple, portable) → upgrade to PostgreSQL when multi-client scales
- **Backend:** Python/FastAPI (lightweight, fast to build)
- **Frontend:** React 19 + Vite + AntD (reuse HOS ERP stack, faster)
- **Auth:** Simple email/password for client portal; API key for RankBuilder agents
- **Hosting:** Run on the existing WSL2/OpenClaw machine, exposed via nginx

---

## Build Priority

### Phase 1 — Core CRM (this build)
1. Lead capture API (what agents write to)
2. Lead database with all fields
3. Client portal: lead list + detail view + status updates
4. Basic dashboard: lead counts, qualification rate, source breakdown
5. HOS email notifications on new qualified leads

### Phase 2 — Agent Integration
6. RankBuilder agent write API (what the outreach engine calls)
7. Lead status transitions via API
8. Multi-channel lead ingestion (HARO, Connectively, Guest Outreach agents)

### Phase 3 — Multi-Client
9. Client onboarding flow
10. White-label portal
11. Cross-client reporting for RankBuilder ops

---

## Out of Scope (Deliberately)
- Full sales pipeline (deals, quotes, invoices)
- Marketing automation beyond lead gen
- Complex workflow automation
- Mobile app
- Third-party integrations (yet)
