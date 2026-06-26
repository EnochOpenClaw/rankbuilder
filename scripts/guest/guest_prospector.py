#!/usr/bin/env python3
"""
Guest Post Prospector
Searches for guest post opportunities in the home improvement / SA niche,
enriches with contact info and DA estimates, stores in prospect DB.
"""

import json
import re
import subprocess
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Add project lib to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from credentials import BREVO_API_KEY

# ============================================================================
# CONFIG
# ============================================================================

PROSPECTS_DIR = Path(__file__).parent.parent.parent / "prospects"
PROSPECTS_DIR.mkdir(exist_ok=True)
PROSPECTS_FILE = PROSPECTS_DIR / "guest_prospects.jsonl"
PROSPECT_DB = PROSPECTS_DIR / "prospect_db.json"

SEARCH_QUERIES = [
    # SA-focused home improvement
    '"write for us" "home improvement" South Africa',
    '"write for us" "renovation" South Africa',
    '"guest post" "shutters" OR "blinds" OR "windows"',
    '"write for us" "outdoor living" South Africa',
    '"submit guest post" "home security"',
    '"write for us" "aluminum" OR "aluminium" windows',
    '"guest post" "flyscreen" OR "fly screen"',
    '"write for us" "security shutters"',
    # Broader home improvement
    '"write for us" "window treatments"',
    '"write for us" "patio" OR "outdoor blinds"',
    '"submit guest post" "home renovation"',
    '"write for us" "DIY" OR "home improvement"',
]

EXCLUDED_DOMAINS = [
    "reddit.com", "quora.com", "linkedin.com", "facebook.com",
    "instagram.com", "pinterest.com", "twitter.com", "youtube.com",
    "wikipedia.org", "github.com", "medium.com", "tumblr.com",
    "wordpress.com", "blogspot.com", "wix.com", "squarespace.com",
    "weebly.com", "godaddy.com", "hostgator.com", "wpengine.com",
    "siteground.com", "bluehost.com", "hubspot.com", "salesforce.com",
]

MAX_PROSPECTS_PER_RUN = 20

# ============================================================================
# STATE
# ============================================================================

def load_prospect_db() -> dict:
    if PROSPECT_DB.exists():
        return json.loads(PROSPECT_DB.read_text())
    return {"prospects": {}, "last_run": None, "total_found": 0}

def save_prospect_db(db: dict):
    PROSPECT_DB.write_text(json.dumps(db, indent=2))

def load_processed_urls() -> set:
    processed = set()
    if PROSPECTS_FILE.exists():
        for line in PROSPECTS_FILE.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if "url" in d:
                    processed.add(d["url"])
    return processed

# ============================================================================
# SEARCH — Using ddgs (DuckDuckGo Python)
# ============================================================================

def search_duckduckgo(query: str) -> list:
    """Search using ddgs, return list of {url, title, snippet}."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=10):
                results.append({
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                })
        return results
    except Exception as e:
        print(f"    Search error: {e}")
        return []

# ============================================================================
# SCRAPING — Get contact info + estimate DA
# ============================================================================

def scrape_prospect_page(url: str) -> dict:
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
        import urllib.request
        
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; RankBuilderBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        
        page_title = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
        if page_title:
            result["page_title"] = page_title.group(1).strip()
        
        # Look for contact email
        emails = re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            html
        )
        valid_emails = [
            e for e in emails 
            if not any(n in e.lower() for n in ['noreply', 'no-reply', 'example', 'test'])
        ]
        if valid_emails:
            result["contact_email"] = valid_emails[0]
        
        # Check for write for us indicators
        write_us_indicators = [
            r'write\s*for\s*us',
            r'guest\s*(post|article|submission)',
            r'submit\s*(article|post|content)',
            r'contribute',
            r'become\s*(a\s*)?contributor',
        ]
        for pattern in write_us_indicators:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_write_for_us"] = True
                break
        
        # Extract topics
        topic_keywords = [
            "home improvement", "renovation", "interior design", "outdoor living",
            "shutters", "blinds", "windows", "doors", "security", "DIY",
            "architecture", "construction", "real estate", "smart home",
            "energy efficiency", "sustainable", "gardens", "landscaping",
        ]
        found_topics = [t for t in topic_keywords if t.lower() in html.lower()]
        result["topics"] = found_topics
        
        domain = urlparse(url).netloc
        result["domain"] = domain
        result["da_estimate"] = estimate_da_from_signals(domain)
        
    except Exception as e:
        result["notes"] = str(e)
    
    return result

def estimate_da_from_signals(domain: str) -> int:
    known_high = {
        "thespruce.com": 89, "hgtv.com": 87, "bhg.com": 86,
        "diynetwork.com": 82, "familyhandyman.com": 78,
        "thisoldhouse.com": 82, "renovation.com": 74, "homeadvisor.com": 76,
        "angi.com": 75, "houzz.com": 83, "pinterest.com": 94,
        "reddit.com": 96, "medium.com": 95, "linkedin.com": 98,
    }
    if domain in known_high:
        return known_high[domain]
    
    blog_platforms = ['wordpress.com', 'blogspot.com', 'wix.com', 'squarespace.com']
    if any(bp in domain for bp in blog_platforms):
        return 25
    
    return 20

# ============================================================================
# SCORING
# ============================================================================

def score_prospect(prospect: dict, search_query: str) -> dict:
    score = 0
    
    topic_matches = len(prospect.get("topics", []))
    score += min(topic_matches * 15, 45)
    
    if prospect.get("contact_email"):
        score += 15
    
    if prospect.get("has_write_for_us"):
        score += 15
    
    da = prospect.get("da_estimate") or 0
    if da >= 50:
        score += 25
    elif da >= 30:
        score += 15
    elif da >= 20:
        score += 5
    
    hos_keywords = ["shutter", "blind", "screen", "window", "door", "security",
                    "outdoor", "patio", "renovation", "aluminum", "aluminium"]
    hos_match = sum(1 for kw in hos_keywords if kw in prospect.get("url", "").lower())
    score += min(hos_match * 5, 20)
    
    prospect["score"] = min(score, 100)
    prospect["best_query"] = search_query
    prospect["scored_at"] = datetime.now().isoformat()
    
    return prospect

# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Starting guest post prospector...")
    
    db = load_prospect_db()
    processed = load_processed_urls()
    new_prospects = []
    
    for query in SEARCH_QUERIES:
        print(f"\n  Searching: {query[:60]}...")
        
        results = search_duckduckgo(query)
        print(f"  → {len(results)} results found")
        
        for r in results[:5]:
            url = r.get("url", "")
            
            if any(ex in url for ex in EXCLUDED_DOMAINS):
                continue
            if url in processed:
                continue
            if url in db["prospects"]:
                continue
            
            print(f"  Scraping: {url[:70]}...")
            prospect = scrape_prospect_page(url)
            prospect["search_title"] = r.get("title", "")
            prospect["search_snippet"] = r.get("snippet", "")
            
            prospect = score_prospect(prospect, query)
            
            if prospect["score"] >= 30:
                print(f"    → Score: {prospect['score']} | DA: {prospect.get('da_estimate')} | "
                      f"Email: {prospect.get('contact_email', 'N/A')}")
                
                db["prospects"][url] = prospect
                new_prospects.append(prospect)
                
                with open(PROSPECTS_FILE, "a") as f:
                    f.write(json.dumps(prospect) + "\n")
            else:
                print(f"    → Skipped (score: {prospect['score']})")
            
            processed.add(url)
            time.sleep(0.5)
        
        if len(new_prospects) >= MAX_PROSPECTS_PER_RUN:
            print(f"\n  Reached max prospects ({MAX_PROSPECTS_PER_RUN}), stopping.")
            break
    
    db["last_run"] = datetime.now().isoformat()
    db["total_found"] = db.get("total_found", 0) + len(new_prospects)
    save_prospect_db(db)
    
    print(f"\n=== Prospector Run Complete ===")
    print(f"New prospects found: {len(new_prospects)}")
    print(f"Total in DB: {len(db['prospects'])}")
    print(f"Top prospects (score >= 60):")
    
    top = sorted(db["prospects"].values(), key=lambda x: x["score"], reverse=True)[:10]
    for p in top:
        print(f"  [{p['score']}] {p['url'][:60]} | {p.get('contact_email', 'no email')}")
    
    return new_prospects

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Guest Post Prospector")
    parser.add_argument("--query", "-q", type=str, help="Single search query")
    parser.add_argument("--limit", "-l", type=int, default=MAX_PROSPECTS_PER_RUN,
                        help=f"Max prospects per run (default: {MAX_PROSPECTS_PER_RUN})")
    parser.add_argument("--status", action="store_true", help="Show current prospect DB")
    
    args = parser.parse_args()
    
    if args.status:
        db = load_prospect_db()
        print(f"Total prospects: {len(db['prospects'])}")
        print(f"Last run: {db.get('last_run', 'never')}")
        print(f"\nTop 20 by score:")
        top = sorted(db["prospects"].values(), key=lambda x: x["score"], reverse=True)[:20]
        for p in top:
            email = p.get("contact_email") or "—"
            topics = ", ".join(p.get("topics", [])[:3])
            print(f"  [{p['score']:3d}] {p['url'][:55]:55s} | {email:30s} | {topics}")
    elif args.query:
        MAX_PROSPECTS_PER_RUN = args.limit
        results = search_duckduckgo(args.query)
        for r in results[:10]:
            print(f"  {r.get('url','')[:70]}")
            print(f"    {r.get('title','')}")
            print(f"    {r.get('snippet','')[:100]}")
            print()
    else:
        new = main()
        print(f"\nDone. {len(new)} new prospects added.")