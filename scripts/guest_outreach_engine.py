#!/usr/bin/env python3
"""
Guest Post Outreach Engine — RankBuilder AI
Autonomous guest post prospecting, pitching, follow-up, and article writing.

Usage:
    python guest_outreach_engine.py discover    # Find new write-for-us pages
    python guest_outreach_engine.py send        # Send daily batch of pitches
    python guest_outreach_engine.py followup    # Send due follow-up emails
    python guest_outreach_engine.py status      # Print outreach pipeline status
    python guest_outreach_engine.py write-article <domain>  # Draft article for accepted prospect

Fortress Blinds: custom aluminium shutters, security shutters,
flyscreen doors/windows, outdoor blinds. 25+ years in SA.
Author: Craig Pauls — manager, hands-on expertise.
"""

import sys
import json
import re
import os
import time
import logging
import textwrap
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths — resolve relative to script location
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent.resolve()
BASE_DIR     = SCRIPT_DIR.parent
PROSPECTS_DB = BASE_DIR / "prospects" / "prospect_db.json"
OUTREACH_LOG = BASE_DIR / "prospects" / "outreach_log.jsonl"
ARTICLES_DIR = BASE_DIR / "prospects" / "articles"
BLOCKED_FILE = BASE_DIR / "blocked" / "blacklist.json"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
LOG_FILE     = SCRIPT_DIR / "logs" / "guest_engine.log"
LOG_FILE.parent.mkdir(exist_ok=True)
ARTICLES_DIR.mkdir(exist_ok=True, parents=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("guest_outreach")

# ---------------------------------------------------------------------------
# Load credentials (Brevo)
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}

_creds = _load_json(CREDENTIALS_FILE)

# Humanize text via Ollama (no external API needed)
import sys as _sys_hg
_sys_hg.path.insert(0, str(BASE_DIR / "lib"))
try:
    from lib.haro_responder import humanize_draft
except Exception:
    humanize_draft = None  # degrade gracefully if Ollama unavailable


def _humanize_html(html_body: str, style: str = "formal") -> tuple[str, dict]:
    """
    Strip HTML tags from html_body, run plain text through humanize_draft(),
    then re-wrap in the same basic HTML structure.

    Returns (humanized_html, humanization_dict).
    """
    if humanize_draft is None:
        return html_body, {}

    # Strip HTML tags to get plain text
    text = re.sub(r'<[^>]+>', ' ', html_body)
    text = re.sub(r'\s+', ' ', text).strip()

    try:
        result = humanize_draft(text, style=style)
        humanized = result["humanized_text"]
        changes = result
    except Exception as ex:
        logging.warning("Humanize failed: %s", ex)
        return html_body, {}

    # Re-wrap humanized text in the same basic HTML structure
    lines = humanized.split('\n')
    wrapped = ''.join(
        f'<p style="margin: 0 0 14px;">{line}</p>' if line.strip() else '<p style="margin: 0 0 6px;">&nbsp;</p>'
        for line in lines
    )
    humanized_html = (
        '<!DOCTYPE html>\n<html>\n<head><meta charset="UTF-8"></head>\n'
        '<body style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; padding: 24px; color: #222;">\n'
        + wrapped +
        '\n</body>\n</html>'
    )

    return humanized_html, changes


FIRECRAWL_KEY = os.environ.get(
    "FIRECRAWL_API_KEY",
    _creds.get("firecrawl", {}).get("api_key", "")
)

# ---------------------------------------------------------------------------
# Brevo email sender (same pattern as connectively_approve.py)
# ---------------------------------------------------------------------------
def _brevo_send(to_email: str, subject: str, html_body: str,
                to_name: str = "Guest Post Editor") -> dict:
    """Send email via Brevo API. Returns dict with success + message_id."""
    import urllib.request, urllib.error

    # Use credentials from lib/ if available
    try:
        sys.path.insert(0, str(BASE_DIR / "lib"))
        from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME
    except Exception:
        BREVO_API_KEY   = os.environ.get("BREVO_API_KEY", "")
        BREVO_ENDPOINT  = "https://api.brevo.com/v3/smtp/email"
        SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "craig@fortressblinds.co.za")
        SENDER_NAME     = "Craig Pauls"

    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": to_name}],
        "htmlContent": html_body,
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BREVO_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json", "api-key": BREVO_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return {"success": True, "message_id": result.get("messageId", "")}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return {"success": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# ARTICLE ANGLE TEMPLATES
# ---------------------------------------------------------------------------
# Each entry: (slug, title, description, suitable_topics)
ARTICLE_ANGLES = [
    {
        "slug": "aluminium-vs-wood-coastal",
        "title": "Aluminium vs Wood Shutters: What Works Best in Coastal Conditions",
        "description": (
            "A practical comparison of aluminium and wood shutters specifically "
            "evaluated for South Africa's coastal climate — salt air, humidity, "
            "UV exposure, and storm resistance. Written from 25+ years of "
            "manufacturer and installer experience."
        ),
        "suitable_topics": [
            "home improvement", "renovation", "interior design", "shutters",
            "blinds", "windows", "doors", "construction", "real estate",
            "DIY", "outdoor living",
        ],
    },
    {
        "slug": "security-shutters-vs-bars",
        "title": "Security Shutters vs Security Bars: A Practical Comparison for SA Homes",
        "description": (
            "Objective analysis of security shutters vs traditional security bars "
            "for South African homeowners — covering deterrent strength, aesthetics, "
            "child safety, fire egress, UV protection, and long-term value. "
            "Insights drawn from decades of SA security-in-home installations."
        ),
        "suitable_topics": [
            "home improvement", "security", "DIY", "construction", "real estate",
            "smart home", "renovation",
        ],
    },
    {
        "slug": "child-pet-safety-screens",
        "title": "Child and Pet Safety with Window Screens: What Parents Need to Know",
        "description": (
            "A guide for parents and pet owners on choosing flyscreen doors and "
            "windows that prevent falls, contain pets, and maintain airflow. "
            "Covers SA coastal/inland standards, mesh strength, tensioning, "
            "and safety certifications."
        ),
        "suitable_topics": [
            "home improvement", "DIY", "renovation", "interior design",
            "family", "parenting", "sustainable", "real estate",
        ],
    },
]

# ---------------------------------------------------------------------------
# PITCH TEMPLATE BUILDER
# ---------------------------------------------------------------------------
PITCH_TEMPLATE = textwrap.dedent("""\
    Hi {editor_name},

    I hope this finds you well. I've been following your blog for a little while
    and particularly enjoyed your recent piece on [{recent_topic}].
    {personal_tie_in}

    I'm Craig Pauls, manager at Fortress Blinds — a South African manufacturer
    and installer of custom aluminium shutters, security shutters,
    flyscreen doors and windows, and outdoor blinds. We've been in the industry
    for over 25 years, working across coastal and inland climates throughout SA.

    I wanted to reach out because I think a guest post could offer real value
    to your readers. Here's an idea I'd love to write for you:

    **[{angle_title}]**
    {angle_description}

    I'd also be happy to write an alternative based on what's most relevant to
    your audience right now — I have several other pieces covering aluminium
    windows in coastal homes, security without sacrificing aesthetics, and
    child-safety with window screens.

    A bit about me: I manage Fortress Blinds' day-to-day operations and
    bring hands-on expertise from decades of site measurements, client
    consultations, and product development. I write from real-world
    experience, not just theory.

    If this sounds like a good fit, I'd love to hear your guest post guidelines
    and preferred topic direction. No pressure if it's not right for your
    audience — I appreciate your time either way.

    Kind regards,
    Craig Pauls
    Manager, Fortress Blinds
    www.fortressblinds.co.za
    {phone_line}
    """)  # phone_line intentionally left blank; we use email as primary

FOLLOWUP_TEMPLATE_1 = textwrap.dedent("""\
    Hi {editor_name},

    Just a gentle nudge on my earlier note — I sent over a guest post pitch
    for [{angle_title}] a few days ago. I understand you're likely busy, so
    no pressure at all if it's not the right fit.

    In short: I run Fortress Blinds, a South African company with 25+ years
    designing and installing shutters, flyscreen doors, and outdoor blinds.
    I'd love to contribute a practical, reader-focused piece to {domain}.

    If you're open to it, I'm happy to send a full draft or discuss a topic
    that better suits your current editorial calendar.

    Thanks for your time — and great work with your blog; the piece on
    [{recent_topic}] was particularly well done.

    Craig
    """)  # noqa: E501

FOLLOWUP_TEMPLATE_2 = textwrap.dedent("""\
    Hi {editor_name},

    Following up on my earlier pitch. I realise inboxes get full quickly!

    To recap quickly: I'm Craig Pauls from Fortress Blinds (25 years in SA's
    window and shutter industry). I'd like to contribute a guest article to
    {domain} — something genuinely useful for your readers, not promotional fluff.

    Here's the idea again: *{angle_title}*
    {angle_short_description}

    If this doesn't align with your editorial plan, I'd appreciate knowing —
    saves me following up unnecessarily. If it does, I'm ready to write
    immediately.

    Either way, wishing you a great week.

    Craig Pauls
    Fortress Blinds | www.fortressblinds.co.za
    """)

FOLLOWUP_TEMPLATE_3 = textwrap.dedent("""\
    Hi {editor_name},

    This will be my final follow-up on the guest post pitch I sent a while back.

    To summarise: Fortress Blinds has 25+ years of expertise in aluminium
    shutters, security shutters, flyscreen doors, and outdoor blinds across
    South Africa. I'd like to offer a single well-researched article for
    {domain}'s readers — no backlinks required (happy to go link-free or
    include a brief, understated bio at the end).

    I'm also open to writing on any topic you'd suggest, adapting to your
    style guide, and handling any revisions at no charge.

    If I don't hear back, I'll take that as a no and won't reach out again.
    I truly appreciate the work you put into {domain} and wish you continued
    success.

    Kind regards,
    Craig Pauls
    Fortress Blinds | www.fortressblinds.co.za
    """)

AUTHOR_BIO = textwrap.dedent("""\
    ---
    **About the Author**
    Craig Pauls is the manager at Fortress Blinds, a South African manufacturer
    and installer of custom aluminium shutters, security shutters,
    flyscreen doors and windows, and outdoor blinds. With over 25 years of
    hands-on experience across coastal and inland SA climates, Craig brings
    practical, field-tested insights to every topic he covers.
    www.fortressblinds.co.za
    """)


# ---------------------------------------------------------------------------
# PROSPECT DATABASE
# ---------------------------------------------------------------------------

def load_prospects() -> dict:
    """Load prospect_db.json and normalise to standard schema.
    Handles both flat dict (direct domain→data) and wrapped dict ({"prospects": {...}}).
    Always returns wrapped dict: {"prospects": {...}, "meta": {...}}.
    """
    if not PROSPECTS_DB.exists():
        return {"prospects": {}, "meta": {"version": "v1", "updated": ""}}

    raw = json.loads(PROSPECTS_DB.read_text())

    # Detect format: if raw has a "prospects" key with dict values, it's wrapped;
    # otherwise the raw dict itself is the prospects dict (flat format).
    if "prospects" in raw and isinstance(raw.get("prospects"), dict):
        entries = raw["prospects"]
        meta = raw.get("meta", {})
    else:
        # Flat format — raw IS the prospects dict
        entries = raw
        meta = {}

    prospects = {}
    for url, entry in entries.items():
        if not isinstance(entry, dict):
            continue  # skip non-dict entries (metadata strings etc.)
        if not entry.get("domain"):
            continue  # skip metadata-like dicts (e.g. {"updated": ..., "domain": "meta"})
        domain = urlparse(url).netloc or urlparse(entry.get("url", url)).netloc
        prospects[url] = {
            "url":              entry.get("url", url),
            "domain":           domain,
            "da":               entry.get("da_estimate", entry.get("da", 20)),
            "traffic":          entry.get("traffic", ""),
            "write_for_us_url": entry.get("write_for_us_url", url),
            "email":            entry.get("contact_email", entry.get("email", "")),
            "topics":           entry.get("topics", []),
            "status":          entry.get("status", "new"),
            "last_contact":    entry.get("last_contact", ""),
            "outreach_count":   entry.get("outreach_count", 0),
            "notes":            entry.get("notes", ""),
            "page_title":      entry.get("page_title", ""),
            "scraped_at":      entry.get("scraped_at", ""),
            "score":           entry.get("score", 50),
            # Enhancer-added fields (preserve these)
            "blocked":          entry.get("blocked", False),
            "block_reason":    entry.get("block_reason", ""),
            "pitch":           entry.get("pitch") or ("READY" if entry.get("email") and entry.get("email") not in ("", "None", "null") else "NEEDS_EMAIL"),
            "quality_score":   entry.get("quality_score", 50),
            "quality_tld":    entry.get("quality_tld", False),
            "tld":             entry.get("tld", ""),
        }
    return {"prospects": prospects, "meta": meta}


def save_prospects(db: dict):
    """Save normalised prospect db to JSON, preserving original extra fields."""
    # Ensure wrapped structure
    if "prospects" not in db:
        db = {"prospects": db, "meta": {"version": "v1", "updated": datetime.now().isoformat()}}
    db["meta"]["updated"] = datetime.now().isoformat()
    PROSPECTS_DB.write_text(json.dumps(db, indent=2, default=str))
    log.info("Saved %d prospects to %s", len(db["prospects"]), PROSPECTS_DB)


def load_blocked() -> set:
    """Load blocked domains + emails from blocklist."""
    blocked = set()
    if BLOCKED_FILE.exists():
        raw = json.loads(BLOCKED_FILE.read_text())
        for item in raw.get("blocked", []):
            if "@" in item:
                blocked.add(item.lower())
            else:
                blocked.add(item.lower().removeprefix("www."))
    return blocked


def get_outreach_log() -> list:
    """Load all outreach log entries (newest first)."""
    entries = []
    if OUTREACH_LOG.exists():
        for line in OUTREACH_LOG.read_text().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)


def append_outreach(entry: dict):
    """Append a single outreach entry to the JSONL log."""
    entry["timestamp"] = datetime.now().isoformat()
    OUTREACH_LOG.open(mode="a", encoding="utf-8").write(json.dumps(entry, default=str) + "\n")


def update_outreach(timestamp: str, updates: dict):
    """Update fields on an outreach log entry (appends new line with merged data)."""
    entries = []
    if OUTREACH_LOG.exists():
        for line in OUTREACH_LOG.read_text().splitlines():
            try:
                e = json.loads(line)
                if e.get("timestamp") == timestamp:
                    e.update(updates)
                entries.append(e)
            except Exception:
                pass
    OUTREACH_LOG.write_text("\n".join(json.dumps(e, default=str) for e in entries) + "\n")


# ---------------------------------------------------------------------------
# ARTICLE ANGLE SELECTOR
# ---------------------------------------------------------------------------

def pick_angle(topics: list) -> dict:
    """Select best article angle based on prospect topic tags."""
    topics_lower = {t.lower() for t in topics}
    # Security/family/parenting → angle 2 or 3
    if any(t in topics_lower for t in ["security", "safety", "family", "parenting"]):
        return next(a for a in ARTICLE_ANGLES if a["slug"] == "security-shutters-vs-bars")
    # Shutters/windows/doors/blinds/aluminium → angle 1
    if any(t in topics_lower for t in ["shutters", "blinds", "windows", "doors", "aluminum", "aluminium", "construction"]):
        return next(a for a in ARTICLE_ANGLES if a["slug"] == "aluminium-vs-wood-coastal")
    # Default: home improvement / renovation / DIY
    return ARTICLE_ANGLES[0]


# ---------------------------------------------------------------------------
# PITCH GENERATOR
# ---------------------------------------------------------------------------

def generate_pitch_text(prospect: dict, angle: dict, followup_n: int = 0) -> tuple[str, str]:
    """
    Generate personalised pitch email subject + HTML body.
    followup_n: 0 = initial, 1-3 = follow-up number.
    Returns (subject, html_body).
    """
    domain    = prospect["domain"]
    topics    = prospect.get("topics", [])
    page_title = prospect.get("page_title", "")
    editor_name = prospect.get("editor_name", "there")

    # Pick a "recent topic" from the page title or topics list
    if page_title:
        recent_topic = re.sub(r"\s*[-|].*$", "", page_title).strip()
        recent_topic = re.sub(r"(?i)(write for us|submit a guest|write for us)", "", recent_topic).strip()
    else:
        recent_topic = topics[0] if topics else "home improvement"

    personal_tie_ins = [
        f"I've noticed your blog covers {recent_topic} in real depth — it shows.",
        f"Your take on {recent_topic} is something I refer clients to regularly.",
        f"The way you approached {recent_topic} really stood out to me.",
    ]
    import random
    personal_tie = random.choice(personal_tie_ins)

    # Subject lines
    subjects = [
        f"Guest post: SA shutter expertise for your readers [{domain}]",
        f"Guest post idea for {domain} — 25 years of SA window insight",
        f"Writer + industry expert wants to contribute to {domain}",
        f"Guest post: {angle['title'][:50]} — thoughts?",
    ]

    if followup_n == 0:
        subject = subjects[0]
        template = PITCH_TEMPLATE
    elif followup_n == 1:
        subject = f"Re: Guest post for {domain} — just checking in"
        template = FOLLOWUP_TEMPLATE_1
    elif followup_n == 2:
        subject = f"Re: Guest post pitch — {angle['title'][:40]}"
        template = FOLLOWUP_TEMPLATE_2
    else:
        subject = f"Final note: guest post for {domain}"
        template = FOLLOWUP_TEMPLATE_3

    # Build the substitution dict
    subs = {
        "editor_name":    editor_name,
        "recent_topic":   recent_topic,
        "personal_tie_in": personal_tie,
        "angle_title":    angle["title"],
        "angle_description": angle["description"],
        "angle_short_description": angle["description"][:120] + "…",
        "domain":         domain,
        "phone_line":     "",
    }

    body = template.format_map(subs)

    # Convert plain-text body to basic HTML
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; padding: 24px; color: #222;">
{''.join(f'<p style="margin: 0 0 14px;">{line}</p>' if line.strip() else '<p style="margin: 0 0 6px;">&nbsp;</p>'
        for line in body.splitlines())}
</body>
</html>"""

    return subject, html_body


# ---------------------------------------------------------------------------
# PROSPECT DISCOVERY (via Firecrawl / web search)
# ---------------------------------------------------------------------------

def discover_prospects(queries: list[str] = None) -> list[dict]:
    """
    Discover new write-for-us pages using Firecrawl search.
    Returns list of normalised prospect dicts.
    """
    if queries is None:
        queries = [
            '"write for us" "home improvement" South Africa',
            '"write for us" "renovation" South Africa',
            '"write for us" "aluminum" OR "aluminium" windows',
            '"write for us" "shutters" OR "blinds"',
            '"submit guest post" "home security" South Africa',
            '"write for us" "outdoor living" South Africa',
        ]

    discovered = []
    seen_urls: set[str] = set()

    # Load existing prospect URLs so we don't re-add
    db = load_prospects()
    for url in db["prospects"]:
        seen_urls.add(url)
        seen_urls.add(db["prospects"][url].get("write_for_us_url", ""))

    for query in queries:
        log.info("Searching: %s", query)
        try:
            # Try Firecrawl search API first
            if FIRECRAWL_KEY:
                import urllib.request, urllib.error
                payload = json.dumps({"query": query, "count": 10}).encode()
                req = urllib.request.Request(
                    "https://api.firecrawl.dev/v0/search",
                    data=payload,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {FIRECRAWL_KEY}"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode())
                results = data.get("data", []) if isinstance(data, dict) else []
            else:
                results = []

        except Exception as e:
            log.warning("Firecrawl search failed for '%s': %s", query, e)
            results = []

        for item in results:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            # Skip generic pages, landing pages, social links
            skip_patterns = ["facebook.com", "twitter.com", "linkedin.com",
                             "instagram.com", "youtube.com", "pinterest.com",
                             "amazon.com", "ebay.com", "aliexpress"]
            if any(p in url.lower() for p in skip_patterns):
                continue

            domain = urlparse(url).netloc.removeprefix("www.")
            description = item.get("description", "")
            page_title  = item.get("title", "")

            # Try to extract topics from description + title
            all_text = f"{page_title} {description}".lower()
            topics = []
            for topic_set in [
                ("shutters", "blinds", "windows", "doors", "aluminium", "aluminum"),
                ("security", "safety"),
                ("renovation", "remodel", "improvement"),
                ("interior design", "decor", " Décor"),
                ("DIY", "do-it-yourself"),
                ("construction", "building"),
                ("outdoor living", "landscaping", "gardens"),
                ("real estate", "property"),
                ("smart home", "automation"),
                ("energy efficiency", "sustainable"),
            ]:
                for t in topic_set:
                    if t in all_text:
                        topics.append(t if len(t) > 4 else topic_set[0])

            prospect = {
                "url":              url,
                "domain":           domain,
                "da":               20,   # Firecrawl doesn't expose DA; default
                "traffic":          "",
                "write_for_us_url": url,
                "email":            "",
                "topics":           list(set(topics)) if topics else ["home improvement"],
                "status":           "new",
                "last_contact":     "",
                "outreach_count":    0,
                "notes":            f"Discovered via search: '{query}'. Score auto-assigned.",
                "page_title":       page_title,
                "scraped_at":       datetime.now().isoformat(),
                "score":            50,
            }
            discovered.append(prospect)
            seen_urls.add(url)
            log.info("  New prospect: %s (%s)", domain, page_title[:60])

        # Be respectful — delay between queries
        time.sleep(1)

    log.info("Discovery complete: %d new prospects found", len(discovered))
    return discovered


def merge_discovered(discovered: list[dict]):
    """Merge discovered prospects into existing database, avoiding duplicates."""
    db = load_prospects()
    added = 0
    for p in discovered:
        url = p["url"]
        if url not in db["prospects"]:
            db["prospects"][url] = p
            added += 1
        elif db["prospects"][url].get("status") == "new" and p.get("email"):
            # Update email if we have it and prospect is still 'new'
            if not db["prospects"][url].get("email"):
                db["prospects"][url]["email"] = p["email"]
    save_prospects(db)
    log.info("Merged %d new prospects into database (total: %d)", added, len(db["prospects"]))


# ---------------------------------------------------------------------------
# OUTREACH SCHEDULER
# ---------------------------------------------------------------------------
DAILY_LIMIT = 10


def get_contacted_domains() -> set[str]:
    """Return set of all domains ever contacted (from outreach log)."""
    domains = set()
    for entry in get_outreach_log():
        domain = entry.get("domain", "")
        if domain:
            domains.add(domain.lower())
    return domains


def get_contacted_this_week() -> dict[str, datetime]:
    """Return dict of domain → last contact date for entries from last 7 days."""
    cutoff = datetime.now() - timedelta(days=7)
    contacted = {}
    for entry in get_outreach_log():
        ts_str = entry.get("timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts >= cutoff:
            domain = entry.get("domain", "").lower()
            if domain:
                contacted[domain] = max(contacted.get(domain, datetime.min), ts)
    return contacted


def build_outreach_candidates(db: dict, contacted_this_week: dict[str, datetime]) -> list[tuple[str, dict]]:
    """
    Build ordered list of (url, prospect) tuples to contact.
    Prioritise: new > waiting (no follow-up sent) > needs_followup,
    filtering out blocked, already-contacted-this-week domains.
    """
    blocked = load_blocked()
    already_contacted_domains = get_contacted_domains()

    candidates = []
    for url, p in db["prospects"].items():
        domain = p["domain"].lower()

        # Skip blocked
        if domain in blocked or (p.get("email") or "").lower() in blocked:
            continue

        # Skip already permanently contacted (accepted/rejected/not_interested)
        if p["status"] in ("accepted", "rejected", "not_interested"):
            continue

        # Skip if already contacted this week
        if domain in contacted_this_week:
            continue

        # Skip if outreach_count > 3 (give up after 4 attempts)
        if p.get("outreach_count", 0) >= 4:
            continue

        # Score prioritisation: new prospects first
        candidates.append((url, p))

    # Sort: new first, then by score desc
    candidates.sort(key=lambda x: (x[1].get("status") != "new", -x[1].get("score", 50)))
    return candidates


def send_daily_batch(limit=10):
    """Send up to `limit` personalised pitches to new/waiting prospects."""
    db = load_prospects()
    contacted_this_week = get_contacted_this_week()
    candidates = build_outreach_candidates(db, contacted_this_week)

    if not candidates:
        log.info("No outreach candidates ready (all contacted recently or queue empty).")
        return

    blocked = load_blocked()
    sent = 0

    for url, prospect in candidates:
        if sent >= limit:
            break

        # Skip if no email known — try to find it or note it
        email = (prospect.get("email") or "").strip()
        if not email or email in ("None", "null", "elements@2x.png"):
            log.info("  Skipping %s — no valid email on file.", prospect["domain"])
            continue

        # Skip blocked emails
        if any(b in email.lower() for b in blocked):
            continue

        angle = pick_angle(prospect.get("topics", []))
        subject, html_body = generate_pitch_text(prospect, angle, followup_n=0)

        # Humanize the pitch body (strip HTML → humanize → re-wrap)
        html_body, hum = _humanize_html(html_body, style="formal")
        if hum:
            log.info("  Humanized: AI score %.1f→%.1f (%s)",
                     hum["original_score"], hum["humanized_score"], hum["changes_summary"])

        # Resolve editor name from email or domain
        name_part = email.split("@")[0]
        editor_name = name_part.replace(".", " ").replace("_", " ").title()
        if editor_name.lower() in ("info", "admin", "hello", "contact", "support", "guests"):
            editor_name = "Guest Post Editor"

        log.info("  Sending to %s <%s> — angle: %s", prospect["domain"], email, angle["slug"])
        result = _brevo_send(email, subject, html_body, to_name=editor_name)

        entry = {
            "domain":       prospect["domain"],
            "prospect_url": url,
            "contact_email": email,
            "subject":      subject,
            "message_id":   result.get("message_id", ""),
            "status":       "sent" if result["success"] else f"failed: {result.get('error', '')}",
            "article_angle": angle["slug"],
            "followup_sequence": [],
            "sent_date":    datetime.now().date().isoformat(),
        }
        append_outreach(entry)

        # Log to tracker
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from outreach_tracker import make_entry, log_event
            tracker_entry = make_entry(
                event='pitch_sent',
                prospect_url=url,
                prospect_domain=prospect['domain'],
                prospect_email=email,
                subject=subject,
                pitch_topic=angle.get('topic', ''),
                pitch_angle=angle.get('slug', ''),
                source='guest_outreach',
            )
            log_event(tracker_entry, quiet=True)
        except Exception as ex:
            log.warning("Tracker logging failed: %s", ex)

        if result["success"]:
            # Update prospect db
            db["prospects"][url]["status"] = "contacted"
            db["prospects"][url]["last_contact"] = datetime.now().isoformat()
            db["prospects"][url]["outreach_count"] = db["prospects"][url].get("outreach_count", 0) + 1
            if not db["prospects"][url].get("email"):
                db["prospects"][url]["email"] = email
            sent += 1
            log.info("  ✅ Sent (message_id=%s)", result.get("message_id", ""))

            # ── CRM: Create lead ─────────────────────────────────────────────
            try:
                from lib.crm_client import get_or_create_lead, mark_lead_sent, CRMError as CRMErr
                lead = get_or_create_lead(
                    source="GUEST_OUTREACH",
                    contact_email=email,
                    contact_name=editor_name,
                    company_name=prospect.get("site_name", prospect["domain"]),
                    company_website=prospect.get("website", f"https://{prospect['domain']}"),
                    source_query=f"Guest post: {angle.get('topic', '')} — {prospect.get('domain', '')}",
                    pitch_sent=html_body[:2000] if html_body else None,
                    quality_score=3,
                )
                mark_lead_sent(lead["id"], pitch_sent=html_body[:2000] if html_body else None)
                log.info("  CRM: created lead %s → SENT", lead["id"])
            except CRMErr as e:
                log.warning("  CRM lead creation failed: %s", e)
        else:
            log.warning("  ❌ Failed: %s", result.get("error", ""))

        time.sleep(2)  # Brevo rate-limit respect

    save_prospects(db)
    log.info("Daily batch complete: %d/%d pitches sent.", sent, min(len(candidates), limit))


# ---------------------------------------------------------------------------
# FOLLOW-UP ENGINE
# ---------------------------------------------------------------------------

def get_followup_sequence_status(log_entry: dict) -> tuple[int, list[dict]]:
    """Parse follow-up sequence from a log entry. Returns (next_followup_n, sequence_list)."""
    seq = log_entry.get("followup_sequence", [])
    if isinstance(seq, list):
        return len(seq), seq
    return 0, []


def should_send_followup(log_entry: dict, followup_n: int) -> bool:
    """Check if a specific follow-up email is due based on the sent date."""
    sent_date_str = log_entry.get("sent_date", "") or log_entry.get("date", "")
    if not sent_date_str:
        try:
            ts = datetime.fromisoformat(log_entry.get("timestamp", "").replace("Z", "+00:00"))
            sent_date_str = ts.date().isoformat()
        except Exception:
            return False

    try:
        sent_date = datetime.fromisoformat(sent_date_str).date()
    except Exception:
        return False

    days_elapsed = (datetime.now().date() - sent_date).days

    # Follow-up windows: 3 days, 7 days, 14 days
    target_days = {1: 3, 2: 7, 3: 14}
    if followup_n not in target_days:
        return False
    return days_elapsed >= target_days[followup_n]


def run_followup_sequence():
    """
    Check all 'sent' entries in outreach log and send follow-ups
    that are due. Enforce max 1 follow-up per domain per week.
    """
    log_entries = get_outreach_log()
    contacted_this_week = get_contacted_this_week()

    # Build lookup by domain for most-recent entry
    domain_latest: dict[str, dict] = {}
    for entry in log_entries:
        d = entry.get("domain", "")
        if d:
            ts = entry.get("timestamp", "")
            if not domain_latest.get(d, {}).get("timestamp") or ts > domain_latest[d]["timestamp"]:
                domain_latest[d] = entry

    db = load_prospects()
    sent_followups = 0

    for domain, entry in domain_latest.items():
        if entry.get("status") not in ("sent", "contacted", "waiting"):
            continue

        # Skip if contacted this week already
        if domain in contacted_this_week:
            continue

        next_n, seq = get_followup_sequence_status(entry)
        if next_n >= 3:
            continue  # Max 3 follow-ups

        if not should_send_followup(entry, next_n + 1):
            continue

        # Find matching prospect in db
        prospect_url = entry.get("prospect_url", "")
        prospect = db["prospects"].get(prospect_url, {})
        if not prospect:
            continue

        # Skip blocked prospects
        if prospect.get("blocked"):
            log.info("  Skipping %s — blocked domain", domain)
            continue

        email = prospect.get("email") or entry.get("contact_email", "")
        if not email:
            continue

        angle = next(
            (a for a in ARTICLE_ANGLES if a["slug"] == entry.get("article_angle")),
            pick_angle(prospect.get("topics", [])),
        )

        followup_n = next_n + 1
        subject, html_body = generate_pitch_text(prospect, angle, followup_n=followup_n)

        # Humanize follow-up body (strip HTML → humanize → re-wrap)
        html_body, hum = _humanize_html(html_body, style="formal")
        if hum:
            log.info("  Humanized: AI score %.1f→%.1f (%s)",
                     hum["original_score"], hum["humanized_score"], hum["changes_summary"])

        editor_name = email.split("@")[0].replace(".", " ").title()
        if editor_name.lower() in ("info", "admin", "hello", "contact", "guests"):
            editor_name = "Guest Post Editor"

        log.info("  Follow-up %d for %s <%s>", followup_n, domain, email)
        result = _brevo_send(email, subject, html_body, to_name=editor_name)

        followup_entry = {
            "followup_n":    followup_n,
            "subject":       subject,
            "message_id":   result.get("message_id", ""),
            "timestamp":     datetime.now().isoformat(),
            "status":        "sent" if result["success"] else f"failed: {result.get('error', '')}",
        }

        # Append to the log entry's sequence
        entry.setdefault("followup_sequence", []).append(followup_entry)
        entry["status"] = f"followup_{followup_n}_sent" if result["success"] else entry["status"]

        if result["success"]:
            sent_followups += 1
            log.info("  ✅ Follow-up %d sent to %s (message_id=%s)", followup_n, domain, result.get("message_id"))

        time.sleep(2)

    log.info("Follow-up run complete: %d follow-ups sent.", sent_followups)


# ---------------------------------------------------------------------------
# RESPONSE TRACKER
# ---------------------------------------------------------------------------

def mark_status(domain: str, new_status: str, note: str = ""):
    """
    Update prospect + outreach log status for a domain.
    Called by Craig when he approves/forwards a reply.
    """
    db = load_prospects()

    for url, p in db["prospects"].items():
        if p["domain"].lower() == domain.lower():
            p["status"] = new_status
            p["notes"] = (p.get("notes", "") + f" [{datetime.now().date().isoformat()}] {note}").strip()
            log.info("Updated %s status -> %s", domain, new_status)

    save_prospects(db)

    # Also update outreach log entries
    if OUTREACH_LOG.exists():
        entries = []
        for line in OUTREACH_LOG.read_text().splitlines():
            try:
                e = json.loads(line)
                if e.get("domain", "").lower() == domain.lower():
                    e["status"] = new_status
                    if note:
                        e["note"] = note
                entries.append(e)
            except Exception:
                pass
        OUTREACH_LOG.write_text("\n".join(json.dumps(e, default=str) for e in entries) + "\n")


# ---------------------------------------------------------------------------
# STATUS REPORTER
# ---------------------------------------------------------------------------

def print_status():
    """Print a human-readable outreach pipeline status."""
    log_entries = get_outreach_log()
    db = load_prospects()

    # Count by status from outreach log
    from collections import Counter
    status_counts = Counter(e.get("status", "unknown") for e in log_entries)

    # Count prospect db statuses
    prospect_statuses = Counter(p.get("status", "new") for p in db["prospects"].values())

    print("\n" + "=" * 65)
    print("  GUEST POST OUTREACH — PIPELINE STATUS")
    print("=" * 65)

    print(f"\n  PROSPECTS DATABASE  ({len(db['prospects'])} total)")
    for s, cnt in sorted(prospect_statuses.items()):
        print(f"    {s:<20} {cnt}")

    print(f"\n  OUTREACH LOG  ({len(log_entries)} total entries)")
    for s, cnt in sorted(status_counts.items()):
        print(f"    {s:<25} {cnt}")

    # Recent activity (last 5)
    print(f"\n  RECENT OUTREACH  (last 5)")
    for entry in log_entries[:5]:
        ts = entry.get("timestamp", "")[:10]
        domain = entry.get("domain", "")
        status = entry.get("status", "")
        print(f"    {ts}  {domain:<30} {status}")

    # Prospects awaiting response
    waiting = [
        (url, p) for url, p in db["prospects"].items()
        if p.get("status") in ("contacted", "waiting")
    ]
    if waiting:
        print(f"\n  AWAITING RESPONSE  ({len(waiting)} prospects)")
        for url, p in sorted(waiting, key=lambda x: x[1].get("last_contact") or "", reverse=True)[:10]:
            last = p.get("last_contact", "never")[:10]
            print(f"    [{p['status']}] {p['domain']:<30} last_contact: {last}  count: {p.get('outreach_count',0)}")

    # Prospects needing follow-up
    print(f"\n  FOLLOW-UP SCHEDULE")
    for entry in log_entries[:20]:
        domain = entry.get("domain", "")
        if entry.get("status") not in ("sent", "contacted"):
            continue
        next_n = len(entry.get("followup_sequence", []))
        if next_n >= 3:
            continue
        sent_str = entry.get("sent_date", entry.get("timestamp","")[:10])
        try:
            sent_date = datetime.fromisoformat(sent_str).date()
        except Exception:
            sent_date = datetime.min
        days_elapsed = (datetime.now().date() - sent_date).days
        target = {1: 3, 2: 7, 3: 14}.get(next_n + 1, 99)
        due_in = target - days_elapsed
        status_flag = "DUE" if due_in <= 0 else f"in {due_in}d"
        print(f"    [{status_flag}] follow-up {next_n+1} for {domain:<30} (sent: {sent_str})")

    accepted = [(url, p) for url, p in db["prospects"].items() if p.get("status") == "accepted"]
    if accepted:
        print(f"\n  ACCEPTED  ({len(accepted)}) — ready for article writing")
        for url, p in accepted:
            print(f"    ✅ {p['domain']}  ({url})")

    print("\n" + "=" * 65 + "\n")


# ---------------------------------------------------------------------------
# ARTICLE WRITER (via Ollama)
# ---------------------------------------------------------------------------

def write_guest_article(domain: str) -> Optional[Path]:
    """
    Draft a full 800-1200 word guest post article for an accepted prospect.
    Saves to prospects/articles/{domain}_{date}.md
    Uses Ollama with kimi-k2.6:cloud or minimax-m2.7:cloud.
    """
    db = load_prospects()
    prospect = None
    for url, p in db["prospects"].items():
        if p["domain"].lower() == domain.lower():
            prospect = p
            break

    if not prospect:
        log.error("Prospect for domain '%s' not found in database.", domain)
        return None

    if prospect.get("status") != "accepted":
        log.warning("Prospect %s status is '%s' (not 'accepted') — proceeding anyway.",
                    domain, prospect.get("status"))

    # Select angle based on topics
    angle = pick_angle(prospect.get("topics", []))
    slug = slugify(domain)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = ARTICLES_DIR / f"{slug}_{date_str}.md"

    log.info("Writing article for %s using angle: %s", domain, angle["slug"])

    # Build the prompt
    system_prompt = textwrap.dedent("""\
        You are Craig Pauls, manager at Fortress Blinds, a South African
        manufacturer and installer of custom aluminium shutters, security shutters,
        flyscreen doors and windows, and outdoor blinds. You have over 25 years of
        hands-on industry experience across coastal and inland South African climates.

        WRITING RULES:
        - Write in a friendly, authoritative, practical tone — not salesy.
        - Aim for 900-1100 words of body content.
        - Use short paragraphs, real-world examples, and specific SA context.
        - Include an author bio section at the end.
        - NO keyword stuffing, NO thin content, NO fluff.
        - Structure with a catchy H2 intro, 3-4 H2 body sections, and a conclusion.
        - Never invent statistics without flagging them as illustrative.
        - Link organically to relevant resources where appropriate.
    """)

    user_prompt = textwrap.dedent(f"""\
        Please write a guest post article for {domain}.

        ARTICLE TITLE: {angle['title']}
        ARTICLE ANGLE: {angle['description']}

        TOPICS / NICHE of the target site: {', '.join(prospect.get('topics', ['home improvement']))}

        Include this author bio at the end (you are Craig Pauls):

        ---
        **About the Author**
        Craig Pauls is the manager at Fortress Blinds, a South African
        manufacturer and installer of custom aluminium shutters, security shutters,
        flyscreen doors and windows, and outdoor blinds. With over 25 years of
        hands-on experience across coastal and inland SA climates, Craig brings
        practical, field-tested insights to every topic he covers.
        www.fortressblinds.co.za
        ---

        Format the output as clean Markdown. Start directly with the article
        (no preamble like "Here is the article"). Include a suggested meta
        description (max 155 characters) as the first line, prefixed with
        META_DESCRIPTION:
    """)

    # Call Ollama
    article_content = None
    for model in ("kimi-k2.6:cloud", "minimax-m2.7:cloud", "llama3.2:latest"):
        result_content = _call_ollama(model, system_prompt, user_prompt)
        if result_content:
            article_content = result_content
            log.info("  Article generated using model: %s", model)
            break
        time.sleep(2)

    if not article_content:
        log.error("All Ollama models failed for article writing.")
        return None

    # Strip any markdown code fences
    article_content = article_content.strip().strip("```markdown").strip("```").strip()

    out_path.write_text(article_content)
    log.info("  Article saved to: %s", out_path)

    # Mark prospect as article_written
    for url, p in db["prospects"].items():
        if p["domain"].lower() == domain.lower():
            p["status"] = "article_written"
            p["article_path"] = str(out_path)
            p["article_angle"] = angle["slug"]
    save_prospects(db)

    return out_path


def _call_ollama(model: str, system: str, prompt: str) -> Optional[str]:
    """Call local Ollama API. Returns text content or None."""
    import urllib.request, urllib.error

    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1400},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "").strip()
    except Exception as e:
        log.warning("  Ollama model '%s' failed: %s", model, e)
        return None


def slugify(text: str) -> str:
    """Convert domain/string to a safe filename slug."""
    import re
    text = text.lower().removeprefix("www.")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[_\s]+", "-", text)
    return text[:60]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_discover(args):
    log.info("=== PROSPECT DISCOVERY ===")
    queries = args.queries if hasattr(args, "queries") and args.queries else None
    discovered = discover_prospects(queries)
    if discovered:
        merge_discovered(discovered)
        log.info("Discovery complete. %d new prospects merged.", len(discovered))
    else:
        log.info("No new prospects discovered.")


def cmd_send(args):
    log.info("=== DAILY OUTREACH BATCH ===")
    limit = getattr(args, 'limit', 10)
    send_daily_batch(limit=limit)


def cmd_followup(args):
    log.info("=== FOLLOW-UP SEQUENCE RUN ===")
    run_followup_sequence()


def cmd_status(args):
    print_status()


def cmd_write_article(args):
    if not args.domain:
        log.error("Please provide a domain: --domain example.com")
        return
    path = write_guest_article(args.domain)
    if path:
        log.info("Article written: %s", path)
        print(f"\n✅ Article saved: {path}\n")
    else:
        log.error("Article writing failed.")
        sys.exit(1)


def cmd_mark(args):
    if not args.domain or not args.status:
        log.error("Usage: --mark --domain example.com --status accepted|rejected|waiting|...")
        return
    mark_status(args.domain, args.status, note=args.note or "")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Guest Post Outreach Engine — RankBuilder AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python guest_outreach_engine.py discover
              python guest_outreach_engine.py send
              python guest_outreach_engine.py followup
              python guest_outreach_engine.py status
              python guest_outreach_engine.py write-article --domain example.com
              python guest_outreach_engine.py mark --domain example.com --status accepted
        """),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # discover
    p = subparsers.add_parser("discover", help="Discover new write-for-us pages")
    p.add_argument("queries", nargs="*", help="Optional custom search queries")

    # send
    p = subparsers.add_parser("send", help="Send daily batch of personalised pitches")
    p.add_argument("--limit", type=int, default=10, help="Max pitches to send per run (default: 10)")

    # followup
    subparsers.add_parser("followup", help="Run follow-up sequence for due prospects")

    # status
    subparsers.add_parser("status", help="Print outreach pipeline status")

    # write-article
    p = subparsers.add_parser("write-article", help="Draft full article for an accepted prospect")
    p.add_argument("--domain", required=True, help="Target domain, e.g. example.com")

    # mark
    p = subparsers.add_parser("mark", help="Manually mark a prospect's status")
    p.add_argument("--domain", required=True)
    p.add_argument("--status", required=True, choices=["new","contacted","waiting","accepted","rejected","not_interested"])
    p.add_argument("--note", default="")

    args = parser.parse_args()

    commands = {
        "discover":      cmd_discover,
        "send":          cmd_send,
        "followup":      cmd_followup,
        "status":        cmd_status,
        "write-article": cmd_write_article,
        "mark":          cmd_mark,
    }

    cmd = commands.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
