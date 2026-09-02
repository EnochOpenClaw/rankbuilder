#!/usr/bin/env python3
"""
Web Search Discovery Runner for RankBuilder Guest Outreach Engine.

Architecture: This script is NOT run directly. Instead, the main session uses
sessions_spawn subagents to run web_search queries via OpenClaw, then merges
the results here.

Usage (from main session):
    python3 -c "
    from scripts.web_search_discovery import merge_search_results
    merge_search_results(json_results_list)
    "

Or via the engine (pending discovery file approach):
    python3 guest_outreach_engine.py discover --source pending

Discovery workflow:
1. Spawn subagents: sessions_spawn with web_search queries
2. Collect JSON results from subagent completions
3. Call merge_search_results() with the combined list
4. Run: python3 guest_outreach_engine.py send

This replaces direct Firecrawl API calls (which time out from WSL2).
"""
import json
import time
from pathlib import Path
from datetime import datetime

import os

# Container path vs local path
CONTAINER_PATH = Path("/app")
LOCAL_PATH    = Path.home() / ".openclaw" / "workspace" / "rankbuilder"
WORKSPACE      = Path("/app") if Path("/app").exists() else LOCAL_PATH
PENDING_FILE  = WORKSPACE / "prospects" / "pending_discovery.json"
OUTREACH_LOG  = WORKSPACE / "prospects" / "outreach_log.jsonl"
PROSPECT_DB   = WORKSPACE / "prospects" / "prospect_db.json"

# High-value SA + home improvement sites to always include (even without email)
SA_SITES = [
    {"url": "https://www.faithful-to-nature.co.za/blog/write-for-us/", "domain": "faithful-to-nature.co.za", "topics": ["home improvement","South Africa","eco-living"]},
    {"url": "https://www.nichemarket.co.za/blog/updates/guest-sponsored-post", "domain": "nichemarket.co.za", "topics": ["home improvement","South Africa"]},
    {"url": "https://www.sprakdesign.com/how-to-decide-between-hiring-an-architect-or-a-designer/", "domain": "sprakdesign.com", "topics": ["renovation","home improvement","South Africa"]},
    {"url": "https://www.southafricanbusinessmatters.co.za/constructionmatters/", "domain": "southafricanbusinessmatters.co.za", "topics": ["construction","home building","South Africa"]},
    {"url": "https://southendstyleblog.com/guest-post.html", "domain": "southendstyleblog.com", "topics": ["home improvement","South Africa"]},
    {"url": "https://www.novafort.co.za/", "domain": "novafort.co.za", "topics": ["home security","home automation","Africa"]},
    {"url": "https://automationafrica.co.za/blogs/", "domain": "automationafrica.co.za", "topics": ["home automation","home security","Africa"]},
    {"url": "https://basecafrica.com/blogs/by-basec-africa/tagged/home-security", "domain": "basecafrica.com", "topics": ["home security","home automation"]},
    {"url": "https://nexusseo.co.za/blog/guest-posting-sa-businesses/", "domain": "nexusseo.co.za", "topics": ["home improvement","South Africa","SEO"]},
    {"url": "https://www.ifsecglobal.com/write-for-us/", "domain": "ifsecglobal.com", "topics": ["home security","security screens","doors"]},
]

SEARCH_QUERIES = [
    # SA-focused
    '"write for us" "home improvement" South Africa',
    '"write for us" renovation South Africa blog',
    '"submit guest post" windows doors South Africa',
    # shutters / security / aluminium
    '"write for us" shutters OR blinds home improvement',
    '"write for us" security shutters OR screens home',
    '"write for us" aluminium OR aluminum windows doors',
    # broader home improvement
    '"write for us" home renovation improvement blog',
    '"write for us" home building construction',
    '"write for us" home security safety Africa',
    '"write for us" outdoor living landscaping South Africa',
    # DIY / interior
    '"write for us" DIY home improvement blog',
    '"write for us" interior design home decor',
    '"write for us" home doors windows exterior SA',
]

def load_seen() -> tuple[set, set]:
    """Returns (seen_domains, seen_urls) from existing DB + outreach log."""
    seen_domains, seen_urls = set(), set()
    if OUTREACH_LOG.exists():
        with open(OUTREACH_LOG) as f:
            for line in f:
                if line.strip():
                    try:
                        e = json.loads(line)
                        d = e.get("domain", "")
                        if d: seen_domains.add(d.lower())
                        u = e.get("prospect_url", "")
                        if u: seen_urls.add(u)
                    except: pass
    if PROSPECT_DB.exists():
        with open(PROSPECT_DB) as f:
            db = json.load(f)
            for p in db.get("prospects", {}).values():
                if p.get("domain"): seen_domains.add(p["domain"].lower())
                if p.get("url"): seen_urls.add(p["url"])
    return seen_domains, seen_urls


def topic_from_text(text: str) -> list[str]:
    text = text.lower()
    topics = []
    buckets = [
        ("shutters/blinds",   ["shutter", "blind", "awning"]),
        ("windows/doors",     ["window", "door", "doorway"]),
        ("aluminium",         ["aluminium", "aluminum"]),
        ("security",         ["security", "safety", "burglar", "break-in"]),
        ("renovation",       ["renovation", "remodel", "improvement", "upgrade"]),
        ("interior design",   ["interior", "decor", "design", "Décor"]),
        ("outdoor living",    ["outdoor", "garden", "landscaping", "patio", "braai"]),
        ("construction",     ["construction", "building", "builder"]),
        ("DIY",              ["diy", "do-it-yourself"]),
        ("real estate",       ["property", "real estate", "homeowner"]),
        ("smart home",        ["smart home", "automation", "iot"]),
    ]
    for topic, keywords in buckets:
        if any(kw in text for kw in keywords):
            topics.append(topic)
    return topics or ["home improvement"]


SKIP_DOMAINS = {
    "adsy.com", "prposting.com", "seosandwitch.com", "guestpostlinks.net",
    "vefogix.com", "design.lexangrit.com", "facebook.com", "twitter.com",
    "linkedin.com", "instagram.com", "youtube.com", "pinterest.com",
    "amazon.com", "ebay.com", "aliexpress.com", "wikipedia.org",
    "reddit.com", "quora.com", "wix.com",
}


def merge_search_results(results: list, seen_domains=None, seen_urls=None) -> int:
    """Merge a list of prospect dicts into prospect_db.json. Returns added count."""
    if not results:
        return 0

    if seen_domains is None or seen_urls is None:
        seen_domains, seen_urls = load_seen()

    db = {"prospects": {}, "total_found": 0, "last_updated": ""}
    if PROSPECT_DB.exists():
        with open(PROSPECT_DB) as f:
            db = json.load(f)

    added = 0
    for item in results:
        url = item.get("url", "")
        domain = item.get("domain", "").lower().removeprefix("www.")
        if not url or not domain:
            continue
        if domain in seen_domains or url in seen_urls:
            continue
        if domain in SKIP_DOMAINS:
            continue

        text = f"{item.get('title','')} {item.get('description','')}"
        topics = item.get("topics") or topic_from_text(text)

        prospect = {
            "url":              url,
            "domain":           domain,
            "email":            item.get("email", "") or "",
            "status":           "new",
            "topics":           topics,
            "score":            50,
            "da":               None,
            "traffic":          None,
            "write_for_us_url": item.get("write_for_us_url", url),
            "last_contact":     "",
            "outreach_count":    0,
            "notes":            f"Discovered via web search. Title: {item.get('title','')[:80]}",
            "page_title":       item.get("title", ""),
            "scraped_at":       datetime.now().isoformat(),
        }
        db["prospects"][url] = prospect
        seen_domains.add(domain)
        seen_urls.add(url)
        added += 1

    db["total_found"] = len(db["prospects"])
    db["last_updated"] = datetime.now().date().isoformat()

    PROSPECT_DB.parent.mkdir(parents=True, exist_ok=True)  # ensure dir exists before write
    with open(PROSPECT_DB, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    return added


def save_pending(results: list):
    """Save raw results to pending file for engine to consume."""
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 web_search_discovery.py merge <results.json>")
        print("       python3 web_search_discovery.py add-sa")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "merge" and len(sys.argv) >= 3:
        with open(sys.argv[2]) as f:
            results = json.load(f)
        added = merge_search_results(results)
        print(f"✅ Merged {added} prospects from {sys.argv[2]}")
    elif cmd == "add-sa":
        added = merge_search_results(SA_SITES)
        print(f"✅ Added {added} SA sites")
    else:
        print("Unknown command")
