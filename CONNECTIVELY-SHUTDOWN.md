# Connectively / HARO — Account Status & Shutdown Notes

**Last updated:** 2026-07-27

---

## ⚠️ ACCOUNT STATUS: CLOSED

**Connectively is permanently shut down.**

All login attempts return "Account does not exist." The platform was retired by Cision on **December 9, 2024**.

---

## History

| Date | Event |
|------|-------|
| 2008 | HARO launched (Help a Reporter Out) |
| ~2022 | HARO acquired by Cision, rebranded as Connectively |
| ~2024 | Cision retired Connectively, migrated users to Qwoted |
| Dec 9, 2024 | Connectively officially shut down |
| Jul 11, 2026 | Last automated emails ("Account does not exist") received |

---

## What This Means for RankBuilder

### ❌ Connectively scraper — DO NOT RUN
- Platform no longer exists
- All automation scripts that scrape `connectively.us` will fail
- The domain returns `DEPLOYMENT_NOT_FOUND`
- Session cookies in `platforms/connectively_cookies.txt` are all expired (Feb 2026)
- The Kasada anti-bot that was blocking Playwright is no longer relevant

### ⚠️ Qwoted — No API, Web Scraping Blocked
- HARO/Connectively migrated to Qwoted (app.qwoted.com)
- Qwoted has **no public API** (confirmed by research, Jul 2026)
- Qwoted uses Vercel with Kasada anti-bot protection — Playwright is blocked
- Even on paid plans ($99–149/mo), no programmatic access available
- Enterprise/Team plans may offer API — email hello@qwoted.com to ask

### ✅ HARO Email Pipeline — STILL WORKING
- HARO queries are still emailed to registered experts
- Emails arrive via **forwarded HARO alerts** to agentdevelopmentops@gmail.com
- The HARO monitor script (haro_monitor.py) processes these emails correctly
- This is the **email-based pipeline**, not the web scraper
- Craig has been forwarding relevant HARO emails manually to trigger automation

---

## HARO/Connectively Credentials (Archived)

| Field | Value |
|-------|-------|
| Email | support@ct-designs.co.za |
| Password | (archived in Vaultwarden — item: Connectively) |
| Session cookies | All expired (last valid: Feb 8, 2026) |
| Platform | Connectively (defunct) |

---

## Current HARO Workflow

```
Journalist posts query on Qwoted (app.qwoted.com)
         ↓
Qwoted emails query to registered expert (support@ct-designs.co.za)
         ↓
Craig forwards relevant query to agentdevelopmentops@gmail.com
         ↓
HARO monitor (haro_monitor.py) parses email → drafts response
         ↓
Response emailed to Craig for approval (haro_approve.py)
         ↓
Craig approves → response submitted via Playwright to HARO portal
         ↓
Lead generated → added to prospect DB
```

---

## Recommended Action

1. **Qwoted API inquiry** — Craig emailed hello@qwoted.com (Jul 27, 2026) asking about API/developer access
   - Enoch (CC'd) will monitor for response
   - If API available: build direct integration
   - If no API: continue email-based manual forwarding

2. **Free Qwoted account** — Create at app.qwoted.com to maintain the HARO query pipeline directly (2 free pitches/month, 2hr delay on delivery)

3. **Disable Connectively cron** — The connectively cron job in `/app/run_crons.sh` should be disabled since the platform is gone

---

## Files This Affects

- `scripts/connectively_monitor.py` — scraper, no longer functional
- `scripts/connectively_approve.py` — approval flow, no longer functional
- `scripts/rewrite_connectively.py` — stealth browser attempt, no longer needed
- `platforms/connectively_cookies.txt` — all cookies expired
- `platforms/connectively_pw.js` — Playwright script, no longer functional

These files can be archived/renamed but should not be deleted until Qwoted API situation is resolved.

---

## Key Lesson

**The HARO pipeline was always email-based, not web-scraping based.**
The web scraper was built for Connectively's web UI — but the actual working pipeline was Craig forwarding emails. The email approach is simpler, more reliable, and not blocked by any anti-bot protection.
