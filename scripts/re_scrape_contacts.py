#!/usr/bin/env python3
"""
re_scrape_contacts.py — Aggressive multi-pass contact discovery for NEEDS_EMAIL prospects.

Passes:
  1. Scrape the stored write-for-us URL with Firecrawl
  2. Try common contact/author/about pages (Firecrawl)
  3. Hunter.io API lookup (domain email patterns)
  4. WHOIS domain contacts

Usage:
  python re_scrape_contacts.py [--domain domain.com] [--all] [--check-only]
"""

import sys
import os
import re
import json
import time
import argparse
import textwrap
from pathlib import Path
from urllib.parse import urlparse, urljoin

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Load credentials
CREDS_FILE = SCRIPT_DIR.parent / "credentials.json"
creds = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
FIRECRAWL_KEY = creds.get("firecrawl_api_key") or os.environ.get("FIRECRAWL_API_KEY", "")
HUNTER_KEY = creds.get("hunter_api_key") or os.environ.get("HUNTER_API_KEY", "")

# Email validation (stricter than before)
SKIP_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tif", "tiff",
             "mp4", "avi", "mov", "mp3", "wav", "pdf", "doc", "docx", "xls", "xlsx"}
FORBIDDEN = re.compile(
    r"(example\.com|sentry\.io|ingest\.|amazonaws\.com|herokuapp\.com|placeholder)",
    re.I
)
BLACKLIST_EMAILS = {
    "no-reply", "noreply", "dont-reply", "admin@", "webmaster@",
    "test@", "foo@", "bar@", "contact@example", "info@example.com",
    "john@doe.com", "jane@doe.com", "test@test.com"
}
BLACKLIST_DOMAINS = {
    "example.com", "localhost", "test.com", "sample.com"
}

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.I
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RankBuilderBot/1.0; +http://rankbuilder.ai/bot)"
}


def is_valid_email(email):
    """Return True if email appears real and deliverable."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    # Forbidden patterns
    if FORBIDDEN.search(email):
        return False
    # Skip blacklist
    if any(b in email.lower() for b in BLACKLIST_EMAILS):
        return False
    # Parse domain
    domain = email.split("@")[1].lower() if "@" in email else ""
    if not domain or len(domain) < 4:
        return False
    # Skip BLACKLIST_DOMAINS
    if any(b in domain for b in BLACKLIST_DOMAINS):
        return False
    # Skip image/file-extension TLDs
    tld = domain.split(".")[-1]
    if tld.lower() in SKIP_TLDS:
        return False
    # Skip domains with no letters (e.g. "150x150.png")
    if not any(c.isalpha() for c in domain):
        return False
    # Skip numericonly domains before the TLD (e.g. 2x3y4z.png)
    main_part = ".".join(domain.split(".")[:-1])
    if main_part and not any(c.isalpha() for c in main_part):
        return False
    return True


def extract_emails(text):
    """Extract and validate emails from raw text."""
    raw = EMAIL_RE.findall(text or "")
    cleaned = []
    for e in raw:
        if is_valid_email(e):
            cleaned.append(e.strip())
    # Dedupe
    seen = set()
    result = []
    for e in cleaned:
        if e.lower() not in seen:
            seen.add(e.lower())
            result.append(e)
    return result


def get_firecrawl(url, path="/ scrape"):
    """Scrape a URL using Firecrawl API, return markdown text."""
    if not FIRECRAWL_KEY:
        return None
    import urllib.request
    import urllib.error

    api_url = "https://api.firecrawl.dev/v1/scrape"
    data = json.dumps({
        "url": url,
        "pageOptions": {"onlyMainContent": True}
    }).encode()
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FIRECRAWL_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("success") and result.get("data"):
                return result["data"].get("content", "")
    except Exception as ex:
        print(f"    Firecrawl error for {url}: {ex}")
    return None


def get_hunter_domain_search(domain):
    """Use Hunter.io domain search API to find email patterns."""
    if not HUNTER_KEY:
        return None
    import urllib.request
    import urllib.parse

    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_KEY}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            emails = data.get("data", {}).get("emails", [])
            if emails:
                return [(e.get("value", ""), e.get("type", ""), e.get("position", ""))
                        for e in emails if e.get("value")]
    except Exception:
        pass
    return None


def get_hunter_email_finder(domain, first_name="", last_name=""):
    """Use Hunter.io email finder to find a specific person's email."""
    if not HUNTER_KEY:
        return None
    import urllib.request

    params = f"domain={domain}&api_key={HUNTER_KEY}"
    if first_name:
        params += f"&first_name={first_name}"
    if last_name:
        params += f"&last_name={last_name}"
    url = f"https://api.hunter.io/v2/email-finder?{params}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            email = data.get("data", {}).get("email", {})
            if email and isinstance(email, str):
                return email
            elif email and isinstance(email, dict):
                return email.get("value")
    except Exception:
        pass
    return None


def scrape_page_for_emails(url):
    """Try Firecrawl on a URL, return extracted emails."""
    text = get_firecrawl(url)
    if text:
        return extract_emails(text)
    # Fallback: simple curl
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "15", "-A", HEADERS["User-Agent"], url],
            capture_output=True, text=True, timeout=20
        )
        return extract_emails(result.stdout)
    except Exception:
        return []


def scrape_domain(domain, write_for_us_url=""):
    """
    Multi-pass scraping for a domain.
    Returns list of (email, source_url, confidence) tuples.
    """
    results = []
    pages_to_try = []

    # Pass 0: Try the write-for-us URL if provided
    if write_for_us_url:
        pages_to_try.append(("wfu_url", write_for_us_url))

    # Pass 1: Common contact/author/about page patterns
    common_paths = [
        "/contact", "/contact-us", "/about", "/about-us", "/author",
        "/guest-post", "/write-for-us", "/submit-guest-post",
        "/become-a-contributor", "/contribute", "/team",
        "/editorial", "/editors", "/staff",
        f"/author/admin", f"/author/editor", f"/author/guest",
    ]
    for path in common_paths:
        pages_to_try.append(("common", f"https://{domain}{path}"))

    # Pass 2: Homepage
    pages_to_try.append(("homepage", f"https://{domain}/"))

    tried = set()
    for pg_type, url in pages_to_try:
        if url in tried:
            continue
        tried.add(url)
        print(f"  [{pg_type:<12}] {url}")
        emails = scrape_page_for_emails(url)
        for email in emails:
            results.append((email, url, pg_type))
        time.sleep(0.5)

    # Pass 3: Hunter.io domain search
    if HUNTER_KEY:
        print(f"  [{'-'.ljust(12)}] Hunter.io domain search: {domain}")
        hunter_results = get_hunter_domain_search(domain)
        if hunter_results:
            for email, em_type, position in hunter_results:
                if is_valid_email(email):
                    results.append((email, "hunter.io", f"hunter:{em_type}"))
        time.sleep(0.3)

    # Dedupe by email
    seen = {}
    for email, url, confidence in results:
        if email.lower() not in seen:
            seen[email.lower()] = (email, url, confidence)

    return list(seen.values())


def update_prospect_email(domain, email, source_url=""):
    """Update prospect email in DB."""
    from guest_outreach_engine import load_prospects, save_prospects

    db = load_prospects()
    prots = db["prospects"]

    # Find the prospect by domain
    key = None
    for k, v in prots.items():
        d = v.get("domain","").replace("www.","")
        if d == domain.replace("www.",""):
            key = k
            break

    if key is None:
        print(f"  Prospect not found in DB: {domain}")
        return False

    old_email = prots[key].get("email","")
    if old_email and is_valid_email(old_email) and old_email != email:
        print(f"  Existing valid email {old_email}, skipping {email}")
        return False

    prots[key]["email"] = email
    if source_url:
        prots[key]["email_source_url"] = source_url
    save_prospects(db)
    print(f"  ✅ Updated {domain}: {email} (from {source_url or 'unknown'})")
    return True


def main():
    parser = argparse.ArgumentParser(description="Re-scrape contacts for NEEDS_EMAIL prospects")
    parser.add_argument("--domain", help="Target domain only")
    parser.add_argument("--all", action="store_true", help="Run on all NEEDS_EMAIL prospects")
    parser.add_argument("--check-only", action="store_true", help="Show what would be scraped, don't update DB")
    parser.add_argument("--passive-only", action="store_true", help="Skip Hunter.io (no API key)")
    args = parser.parse_args()

    from guest_outreach_engine import load_prospects

    if args.domain:
        targets = [(args.domain, "")]  # (domain, wfu_url)
    elif args.all:
        db = load_prospects()
        prots = db["prospects"]
        targets = [
            (v.get("domain",""), v.get("write_for_us_url",""))
            for k, v in prots.items()
            if v.get("pitch") in ("NEEDS_EMAIL", "BLOCKED")
            and v.get("domain")
        ]
    else:
        print("Use --domain DOMAIN or --all")
        return

    total_found = 0
    total_updated = 0

    for domain, wfu_url in targets:
        domain = domain.replace("www.","")
        print(f"\n{'='*60}")
        print(f"Scraping: {domain}")
        if wfu_url:
            print(f"  Write-for-us URL: {wfu_url}")

        results = scrape_domain(domain, wfu_url if wfu_url.startswith("http") else "")

        # Filter to valid emails only
        valid = [(e, url, conf) for e, url, conf in results if is_valid_email(e)]

        if not valid:
            print(f"  ❌ No valid emails found")
            total_found += 0
            continue

        print(f"\n  Found {len(valid)} email(s):")
        for email, url, conf in valid:
            print(f"    • {email:<50} (conf: {conf})")

        if args.check_only:
            print(f"  [check-only] Not updating DB")
        else:
            # Pick the best email (prefer direct contact emails over general ones)
            # Priority: editor@ > contact@ > info@ > other
            priority = {"editor": 0, "contact": 1, "write": 2, "info": 3, "hunter": 4, "common": 5, "wfu_url": 6, "homepage": 7, "default": 8}
            def email_priority(e):
                local = e[0].split("@")[0].lower()
                for kw, p in priority.items():
                    if kw in local:
                        return p
                return priority["default"]
            valid_sorted = sorted(valid, key=email_priority)
            best_email, best_url, best_conf = valid_sorted[0]

            updated = update_prospect_email(domain, best_email, source_url=best_url)
            if updated:
                total_updated += 1

        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Done. Updated {total_updated} prospects.")

if __name__ == "__main__":
    main()
