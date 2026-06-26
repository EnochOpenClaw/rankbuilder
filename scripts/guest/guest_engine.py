#!/usr/bin/env python3
"""
Guest Post Outreach Engine — Orchestrator

Ties the full guest post pipeline together:
  discover → draft → submit → track

Single entry point for both manual runs and cron automation.

Usage:
  python3 guest_engine.py --discover        Find and score new prospects
  python3 guest_engine.py --draft           Generate pitches for top prospects
  python3 guest_engine.py --run             Full pipeline: discover + draft + submit
  python3 guest_engine.py --report          Show pipeline status
  python3 guest_engine.py --test-ollama     Test Ollama connectivity
"""

import json
import re
import sys
import time as time_mod
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# ── Project paths ────────────────────────────────────────────────────────────

RANKBUILDER = Path.home() / ".openclaw/workspace/rankbuilder"
SYS_LIB     = RANKBUILDER / "lib"
PROSPECTS   = RANKBUILDER / "prospects"
PITCHES     = PROSPECTS / "pitches"
OUTREACH_LOG = PROSPECTS / "outreach_log.jsonl"

sys.path.insert(0, str(SYS_LIB))
from credentials import BREVO_API_KEY, SENDER_EMAIL, SENDER_NAME, NOTIFY_EMAIL

# ── Config ─────────────────────────────────────────────────────────────────

BRAND_CONTEXT = {
    "company":    "Fortress Blinds",
    "founder":    "Craig Pauls",
    "location":   "South Africa",
    "website":    "https://fortressblinds.co.za",
    "email":      "craig@fortressblinds.co.za",
    "specialties": [
        "Custom aluminium shutters",
        "Security shutters and outdoor blinds",
        "Flyscreen doors and windows",
        "Aluminum door and window openings",
        "Residential and commercial installations",
    ],
    "unique_angle": (
        "South African climate expertise — coastal salt air resistance, "
        "heat/UV management, storm protection. 25+ years of hands-on experience. "
        "Works with homeowners, architects, and developers."
    ),
    "topics_offered": [
        ("shutters", [
            "The complete guide to choosing the right shutters for South African homes",
            "Aluminum vs wood shutters: what works best in coastal conditions",
            "Security shutters: peace of mind without sacrificing aesthetics",
            "Motorized vs manual shutters: is automation worth the investment?",
        ]),
        ("flyscreen", [
            "Why flyscreen doors are essential for South African outdoor living",
            "Pet-safe flyscreen solutions: keep your pets in, pests out",
            "How to choose the right mesh for your climate zone",
        ]),
        ("outdoor", [
            "Creating the perfect outdoor entertainment area in SA",
            "Outdoor blinds vs shutters: what's the difference?",
            "Shade solutions for South African summers: what actually works",
            "Patio enclosures: extending your living space year-round",
        ]),
        ("energy", [
            "How shutters can reduce your cooling costs by up to 40%",
            "Thermal efficiency: the often-overlooked benefit of quality shutters",
            "Energy-efficient windows and doors: where to invest your budget",
        ]),
        ("security", [
            "Home security in 2026: what homeowners are prioritizing",
            "Security shutters vs security bars: a practical comparison",
            "Child and pet safety with window screens: what parents need to know",
        ]),
    ]
}

EXCLUDED_DOMAINS = {
    "reddit.com", "quora.com", "linkedin.com", "facebook.com",
    "instagram.com", "pinterest.com", "twitter.com", "youtube.com",
    "wikipedia.org", "github.com", "medium.com", "tumblr.com",
    "wordpress.com", "blogspot.com", "wix.com", "squarespace.com",
    "weebly.com", "godaddy.com", "hostgator.com", "wpengine.com",
    "siteground.com", "bluehost.com", "hubspot.com", "salesforce.com",
}

SEARCH_QUERIES = [
    '"write for us" "home improvement" South Africa',
    '"write for us" "renovation" South Africa',
    '"guest post" "shutters" OR "blinds" OR "windows"',
    '"write for us" "outdoor living" South Africa',
    '"submit guest post" "home security"',
    '"write for us" "aluminum" OR "aluminium" windows',
    '"guest post" "flyscreen" OR "fly screen"',
    '"write for us" "security shutters"',
    '"write for us" "window treatments"',
    '"write for us" "patio" OR "outdoor blinds"',
    '"submit guest post" "home renovation"',
    '"write for us" "DIY" OR "home improvement"',
]

MAX_DISCOVER_PER_RUN = 15
MAX_DRAFT_PER_RUN    = 5
MIN_SCORE_FOR_DRAFT  = 50
COOLDOWN_DAYS        = 14
OLLAMA_MODEL         = "kimi-k2.6:cloud"
OLLAMA_TIMEOUT       = 90

PITCH_STATUS_DRAFT   = "draft"
PITCH_STATUS_PENDING = "pending_approval"
PITCH_STATUS_SENT    = "sent"
PITCH_STATUS_SKIPPED = "skipped"

# ── Helpers ─────────────────────────────────────────────────────────────────

def load_prospect_db() -> dict:
    db_file = PROSPECTS / "prospect_db.json"
    if db_file.exists():
        return json.loads(db_file.read_text())
    return {"prospects": {}, "last_discovery": None}


def save_prospect_db(db: dict):
    (PROSPECTS / "prospect_db.json").write_text(json.dumps(db, indent=2))


def load_outreach_log() -> list:
    if not OUTREACH_LOG.exists():
        return []
    return [json.loads(l) for l in OUTREACH_LOG.read_text().splitlines() if l.strip()]


def load_pitches() -> list:
    if not PITCHES.exists():
        return []
    return [json.loads(f.read_text()) for f in PITCHES.glob("pitch_*.json")]


def get_pitched_domains(cooldown_days: int = COOLDOWN_DAYS) -> set:
    cutoff = datetime.now() - timedelta(days=cooldown_days)
    cutoff_iso = cutoff.isoformat()
    domains = set()
    for entry in load_outreach_log():
        ts = entry.get("timestamp", "")
        if not ts:
            continue
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                url = entry.get("prospect_url", "")
                if url:
                    domains.add(urlparse(url).netloc)
        except Exception:
            pass
    for p in load_pitches():
        if p.get("created_at", "") >= cutoff_iso and p.get("status") == PITCH_STATUS_SENT:
            domains.add(urlparse(p.get("prospect_url", "")).netloc)
    return domains


def get_pitched_urls() -> set:
    return {p.get("prospect_url") for p in load_pitches()}


def get_today_send_count() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    return sum(
        1 for e in load_outreach_log()
        if e.get("timestamp", "").startswith(today) and e.get("status") == PITCH_STATUS_SENT
    )


def estimate_da(domain: str) -> int:
    known = {
        "thespruce.com": 89, "hgtv.com": 87, "bhg.com": 86,
        "diynetwork.com": 82, "familyhandyman.com": 78,
        "thisoldhouse.com": 82, "renovation.com": 74, "homeadvisor.com": 76,
        "angi.com": 75, "houzz.com": 83,
        "pinterest.com": 94, "reddit.com": 96, "medium.com": 95,
        "linkedin.com": 98,
    }
    if domain in known:
        return known[domain]
    if any(bp in domain for bp in ["wordpress.com","blogspot.com","wix.com","squarespace.com"]):
        return 25
    return 20


def score_prospect(prospect: dict) -> int:
    score = 0
    score += min(len(prospect.get("topics", [])) * 15, 45)
    if prospect.get("contact_email"):
        score += 15
    if prospect.get("has_write_for_us"):
        score += 15
    da = prospect.get("da_estimate") or 0
    if da >= 50:   score += 25
    elif da >= 30: score += 15
    elif da >= 20: score += 5
    hos_kw = ["shutter","blind","screen","window","door","security",
              "outdoor","patio","renovation","aluminum","aluminium"]
    score += min(sum(1 for kw in hos_kw if kw in prospect.get("url","").lower()) * 5, 20)
    return min(score, 100)


def scrape_page(url: str) -> dict:
    result = {
        "url": url,
        "scraped_at": datetime.now().isoformat(),
        "contact_email": None,
        "topics": [],
        "da_estimate": None,
        "has_write_for_us": False,
        "notes": "",
    }
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RankBuilderBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        title_m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_m:
            result["page_title"] = title_m.group(1).strip()

        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
        result["contact_email"] = next(
            (e for e in emails
             if not any(n in e.lower() for n in ["noreply","no-reply","example","test","admin"])),
            None
        )

        result["has_write_for_us"] = bool(
            re.search(
                r"write\s*for\s*us|guest\s*post|submit\s*article|contribute|become\s*contributor",
                html, re.IGNORECASE
            )
        )

        topic_kw = [
            "home improvement","renovation","interior design","outdoor living",
            "shutters","blinds","windows","doors","security","DIY",
            "architecture","construction","real estate","smart home",
            "energy efficiency","sustainable","gardens","landscaping",
        ]
        result["topics"] = [t for t in topic_kw if t.lower() in html.lower()]
        result["domain"] = urlparse(url).netloc
        result["da_estimate"] = estimate_da(result["domain"])

    except Exception as e:
        result["notes"] = str(e)

    return result


# ── Stage 1: Discover ───────────────────────────────────────────────────────

def run_discover(max_new: int = MAX_DISCOVER_PER_RUN) -> list:
    from ddgs import DDGS

    db             = load_prospect_db()
    pitched_urls   = get_pitched_urls()
    pitched_domains = get_pitched_domains()
    new_prospects  = []

    print(f"\n[{datetime.now():%H:%M}] 🔍 Discovery run — max {max_new} new prospects...")

    for query in SEARCH_QUERIES:
        if len(new_prospects) >= max_new:
            break

        print(f"  Searching: {query[:55]}...", end=" ", flush=True)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=8))
        except Exception as e:
            print(f"Error: {e}")
            continue
        print(f"→ {len(results)} results")

        for r in results[:6]:
            if len(new_prospects) >= max_new:
                break

            url = r.get("href", "")
            if not url:
                continue
            domain = urlparse(url).netloc

            if any(ex in domain for ex in EXCLUDED_DOMAINS):
                continue
            if url in pitched_urls:
                continue
            if domain in pitched_domains:
                continue
            if url in db["prospects"]:
                continue

            print(f"    Scraping {url[:60]}...", end=" ", flush=True)
            prospect = scrape_page(url)
            prospect["search_title"]   = r.get("title", "")
            prospect["search_snippet"] = r.get("body", "")
            prospect["score"]          = score_prospect(prospect)
            prospect["best_query"]     = query
            prospect["scored_at"]      = datetime.now().isoformat()

            if prospect["score"] >= 30:
                print(f"✓ score={prospect['score']} da={prospect.get('da_estimate')} "
                      f"email={'yes' if prospect.get('contact_email') else 'no'}")
                db["prospects"][url] = prospect
                new_prospects.append(prospect)
                (PROSPECTS / "guest_prospects.jsonl").open("a").write(
                    json.dumps(prospect) + "\n"
                )
            else:
                print(f"✗ score={prospect['score']} (too low)")

            time_mod.sleep(0.4)

    db["last_discovery"] = datetime.now().isoformat()
    save_prospect_db(db)

    print(f"\n✅ Discovery complete: {len(new_prospects)} new prospects added")
    for p in sorted(new_prospects, key=lambda x: x["score"], reverse=True)[:5]:
        print(f"  [{p['score']}] {p['url'][:60]} | DA {p.get('da_estimate')} | "
              f"{'📧' if p.get('contact_email') else '❌no email'}")

    return new_prospects


# ── Stage 2: Draft ──────────────────────────────────────────────────────────

def generate_pitch_via_ollama(prospect: dict) -> dict:
    domain     = urlparse(prospect["url"]).netloc
    page_title = prospect.get("page_title", domain)
    contact    = prospect.get("contact_email", "")
    topics     = prospect.get("topics", [])
    da         = prospect.get("da_estimate", "?")

    article_options = None
    for t, ideas in BRAND_CONTEXT["topics_offered"]:
        if t in " ".join(topics).lower() or any(t in top.lower() for top in topics):
            article_options = ideas
            break
    if not article_options:
        article_options = BRAND_CONTEXT["topics_offered"][0][1]

    article_str = "\n".join(f"- {idea}" for idea in article_options)

    prompt = f"""You are drafting a guest post pitch email for a South African home improvement expert.

## THE WEBSITE WE'RE PITCHING
- Domain: {domain}
- Page: {page_title}
- Domain Authority estimate: {da}
- Accepted topics: {', '.join(topics) if topics else 'home improvement'}
- Contact email: {contact}

## ABOUT OUR CLIENT
Craig Pauls is the manager at {BRAND_CONTEXT['company']}, a South African company:
{chr(10).join(f'  - {s}' for s in BRAND_CONTEXT['specialties'])}

Website: {BRAND_CONTEXT['website']}
Unique angle: {BRAND_CONTEXT['unique_angle']}

## ARTICLE IDEAS WE CAN WRITE
{article_str}

## YOUR TASK
Draft a professional, personalized guest post pitch email that:
1. Has a compelling subject line (under 60 chars, no spamminess)
2. Opens with a genuine, specific compliment about their site (1-2 sentences)
3. Briefly introduces Craig as a South African home improvement expert
4. Proposes 1-2 specific article ideas from the list above (or a relevant alternative)
5. Highlights why this article would resonate with their audience
6. Includes a short author bio (2-3 sentences)
7. Ends with a clear, low-pressure call to action
8. Feels personal, not mass-emailed

## TONE
Professional, warm, confident. Not salesy. Just a knowledgeable person offering real value.

## OUTPUT FORMAT
Return JSON with these exact fields:
{{
  "subject": "subject line here",
  "greeting": "Hi [name or 'there']",
  "body": "full email body here",
  "article_proposal": "title of article idea",
  "author_bio": "2-3 sentence bio",
  "signoff": "Kind regards"
}}

Write only valid JSON. No markdown. No explanation. Start with {{ and end with }}."""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.8, "num_predict": 1024}
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode())
        text = result.get("response", "").strip()
        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^```\s*", "", text).strip().rstrip("```").rstrip()
        return json.loads(text)
    except Exception as e:
        return {
            "error": str(e),
            "subject": f"Guest post idea — {domain}",
            "body": f"Pitch generation failed: {e}",
            "article_proposal": "Error",
            "greeting": "Hi there",
            "author_bio": "",
            "signoff": "Kind regards",
        }


def run_draft(max_pitches: int = MAX_DRAFT_PER_RUN) -> list:
    db             = load_prospect_db()
    pitched_urls    = get_pitched_urls()
    pitched_domains = get_pitched_domains()
    existing_urls  = {p.get("prospect_url") for p in load_pitches()}

    candidates = []
    for url, prospect in db["prospects"].items():
        if url in existing_urls or url in pitched_urls:
            continue
        domain = urlparse(url).netloc
        if domain in pitched_domains:
            continue
        if prospect.get("score", 0) < MIN_SCORE_FOR_DRAFT:
            continue
        if not prospect.get("contact_email"):
            continue
        candidates.append((url, prospect))

    candidates.sort(key=lambda x: x[1].get("score", 0), reverse=True)
    to_draft = candidates[:max_pitches]

    if not to_draft:
        print(f"\n[{datetime.now():%H:%M}] 📝 No prospects need pitching right now.")
        return []

    print(f"\n[{datetime.now():%H:%M}] 📝 Drafting {len(to_draft)} pitches...")
    generated = []

    for url, prospect in to_draft:
        print(f"\n  [{prospect['score']}] {url[:60]}")
        print(f"    DA: {prospect.get('da_estimate')} | Topics: {', '.join(prospect.get('topics',[])[:3])}")

        data = generate_pitch_via_ollama(prospect)

        if "error" in data:
            print(f"    ❌ Ollama error: {data['error']}")
            continue

        pitch = {
            "prospect_url":     url,
            "prospect_score":   prospect.get("score", 0),
            "prospect_da":      prospect.get("da_estimate", 0),
            "contact_email":    prospect.get("contact_email", ""),
            "article_proposal": data.get("article_proposal", ""),
            "subject":           data.get("subject", ""),
            "greeting":         data.get("greeting", "Hi there"),
            "body":             data.get("body", ""),
            "author_bio":       data.get("author_bio", ""),
            "signoff":          data.get("signoff", "Kind regards"),
            "created_at":       datetime.now().isoformat(),
            "status":           PITCH_STATUS_DRAFT,
        }

        safe_name = re.sub(r"[^a-zA-Z0-9]", "_", urlparse(url).netloc)
        pitch_file = PITCHES / f"pitch_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        pitch_file.write_text(json.dumps(pitch, indent=2))

        print(f"    ✅ Pitch saved: {pitch_file.name}")
        print(f"    📌 Article: {pitch['article_proposal']}")
        generated.append(pitch)
        time_mod.sleep(2)

    print(f"\n✅ Generated {len(generated)} pitches")
    return generated


# ── Stage 3: Submit ─────────────────────────────────────────────────────────

def send_approval_email(pitch: dict) -> dict:
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
      <h2 style="color: #1a1a2e;">📋 Guest Post Pitch — Approval Needed</h2>
      <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <p><strong>📌 Article:</strong> {pitch.get('article_proposal','')}</p>
        <p><strong>🎯 Target:</strong> <a href="{pitch.get('prospect_url','')}">{pitch.get('prospect_url','')}</a></p>
        <p><strong>📧 To:</strong> {pitch.get('contact_email','')}</p>
        <p><strong>⭐ Score:</strong> {pitch.get('prospect_score','')} | <strong>🌐 DA:</strong> {pitch.get('prospect_da','')}</p>
      </div>
      <h3>Subject:</h3>
      <p style="background: #e8f4fd; padding: 10px; border-radius: 5px;">{pitch.get('subject','')}</p>
      <h3>Email Body:</h3>
      <div style="background: #fff; border: 1px solid #ddd; padding: 20px; border-radius: 5px; white-space: pre-wrap;">{pitch.get('body','')}</div>
      <h3>Author Bio:</h3>
      <p style="color: #555;">{pitch.get('author_bio','')}</p>
      <hr style="margin: 30px 0;">
      <h3>🚀 To Send:</h3>
      <p><strong>Reply YES</strong> → Send this pitch now<br>
      <strong>Reply SKIP</strong> → Discard this pitch<br>
      <strong>Reply EDIT [new text]</strong> → Send with your edits</p>
      <p style="color: #888; font-size: 12px; margin-top: 20px;">
        Generated by RankBuilder AI on {datetime.now():%Y-%m-%d %H:%M}
      </p>
    </div>
    """

    payload = json.dumps({
        "sender": {"email": SENDER_EMAIL, "name": SENDER_NAME},
        "to": [{"email": NOTIFY_EMAIL, "name": "Craig"}],
        "subject": f"📋 [GUEST POST APPROVAL] {pitch.get('subject','')}",
        "htmlContent": html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={"Content-Type": "application/json", "api-key": BREVO_API_KEY},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return {"success": True, "message_id": result.get("messageId", "")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_submit(max_per_run: int = 3) -> list:
    pitches = [p for p in load_pitches() if p.get("status") == PITCH_STATUS_DRAFT]
    if not pitches:
        print(f"\n[{datetime.now():%H:%M}] No draft pitches to submit.")
        return []

    today_sent = get_today_send_count()
    remaining  = 10 - today_sent
    to_submit  = min(len(pitches), remaining, max_per_run)

    print(f"\n[{datetime.now():%H:%M}] 📤 Submitting {to_submit} pitches for approval...")
    submitted = []

    for pitch in pitches[:to_submit]:
        result = send_approval_email(pitch)
        if result.get("success"):
            pitch["status"]       = PITCH_STATUS_PENDING
            pitch["submitted_at"] = datetime.now().isoformat()
            for f in PITCHES.glob("pitch_*.json"):
                existing = json.loads(f.read_text())
                if (existing.get("prospect_url") == pitch.get("prospect_url") and
                        existing.get("created_at") == pitch.get("created_at")):
                    f.write_text(json.dumps(pitch, indent=2))
                    break
            print(f"  ✅ Submitted: {pitch.get('article_proposal','')[:50]}")
            print(f"     → {pitch.get('prospect_url','')[:50]}")
            submitted.append(pitch)
        else:
            print(f"  ❌ Failed: {pitch.get('prospect_url','')}")
            print(f"     Error: {result.get('error','')}")

    print(f"\n✅ {len(submitted)} pitches submitted for approval")
    return submitted


# ── Report ─────────────────────────────────────────────────────────────────

def run_report():
    db      = load_prospect_db()
    pitches = load_pitches()
    log     = load_outreach_log()

    by_status = {}
    for p in pitches:
        by_status[p.get("status", "unknown")] = by_status.get(p.get("status", "unknown"), 0) + 1

    today_sent    = get_today_send_count()
    pitched_domains = get_pitched_domains()
    last_disc     = db.get("last_discovery") or db.get("last_run") or "never"

    print(f"""
╔══════════════════════════════════════════════════════╗
║       Guest Post Outreach Engine — Pipeline Status  ║
╠══════════════════════════════════════════════════════╣
║  Prospects in DB      : {len(db['prospects']):>4}                        ║
║  Last discovery       : {str(last_disc):>25}  ║
║  Total pitches        : {len(pitches):>4}                        ║
║  Pitches by status:                                   ║""")
    for s, n in sorted(by_status.items()):
        print(f"║    {s:<20}: {n:>4}                        ║")
    print(f"""║  Today's sends       : {today_sent:>4} / 10                    ║
║  Domains in cooldown  : {len(pitched_domains):>4}                        ║
║  Outreach log entries : {len(log):>4}                        ║
╚══════════════════════════════════════════════════════╝""")

    pitched_urls  = {p.get("prospect_url") for p in load_pitches()}
    needs_pitch = [
        (url, p) for url, p in db["prospects"].items()
        if url not in pitched_urls
        and p.get("score", 0) >= MIN_SCORE_FOR_DRAFT
        and p.get("contact_email")
        and urlparse(url).netloc not in get_pitched_domains()
    ]
    needs_pitch.sort(key=lambda x: x[1].get("score", 0), reverse=True)

    if needs_pitch:
        print(f"\n📋 Top prospects ready for pitching ({len(needs_pitch)} total):")
        for url, p in needs_pitch[:8]:
            email_flag = "📧" if p.get("contact_email") else "❌"
            print(f"  [{p.get('score')}] {email_flag} {url[:55]}")
            print(f"         DA:{p.get('da_estimate')} | {', '.join(p.get('topics',[])[:2])}")


# ── Ollama test ─────────────────────────────────────────────────────────────

def test_ollama():
    print(f"Testing Ollama ({OLLAMA_MODEL})...", end=" ", flush=True)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": "Say 'OK' in one word.",
        "stream": False,
        "options": {"num_predict": 5}
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        print(f"✅ Response: {result.get('response','').strip()}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Guest Post Outreach Engine")
    parser.add_argument("--discover",   action="store_true", help="Find and score new prospects")
    parser.add_argument("--draft",      action="store_true", help="Generate pitches for top prospects")
    parser.add_argument("--submit",     action="store_true", help="Submit draft pitches for Craig's approval")
    parser.add_argument("--run",        action="store_true", help="Full pipeline: discover + draft + submit")
    parser.add_argument("--report",     action="store_true", help="Show pipeline status")
    parser.add_argument("--test-ollama", action="store_true", help="Test Ollama connectivity")
    parser.add_argument("--max-new",    type=int, default=MAX_DISCOVER_PER_RUN, help="Max new prospects per discover")
    parser.add_argument("--max-draft",  type=int, default=MAX_DRAFT_PER_RUN,     help="Max pitches per draft run")
    args = parser.parse_args()

    PITCHES.mkdir(exist_ok=True)

    if args.test_ollama:
        test_ollama()
    elif args.report:
        run_report()
    elif args.run:
        print(f"\n{'='*50}")
        print(f"  Guest Post Engine — Daily Pipeline Run")
        print(f"{'='*50}")
        run_discover(max_new=args.max_new)
        run_draft(max_pitches=args.max_draft)
        run_submit()
        run_report()
    elif args.discover:
        run_discover(max_new=args.max_new)
    elif args.draft:
        run_draft(max_pitches=args.max_draft)
    elif args.submit:
        run_submit()
    else:
        parser.print_help()