#!/usr/bin/env python3
"""
scrape_contact_pages.py — Batch email scraper for write-for-us pages.
Scrapes missing contact emails from prospects that have a write-for-us URL
but no email on file.
"""

import json
import re
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

try:
    from firecrawl import FirecrawlApp
    from credentials import FIRECRAWL_API_KEY
    HAS_FIRECRAWL = bool(FIRECRAWL_API_KEY)
except Exception:
    HAS_FIRECRAWL = False

DB_FILE   = Path(__file__).parent.parent / 'prospects' / 'prospect_db.json'
LOG_FILE  = Path(__file__).parent / 'logs' / 'scrape_contact.log'
OUTPUT    = Path(__file__).parent / 'prospects' / 'scraped_emails.json'

LOG_FILE.parent.mkdir(exist_ok=True)

# Regex patterns for common contact page email formats
EMAIL_RE  = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
FORBIDDEN = re.compile(r'(noreply|no-reply|example|test@|localhost|domain\.com)', re.I)

BLACKLIST_EMAILS = {
    'mailer-daemon', 'postmaster', 'nobody', 'root', 'admin', 'webmaster',
    'info@', 'contact@', 'hello@', 'support@', 'noreply@', 'no-reply@',
    'donotreply@', 'privacy@', 'terms@',
}
BLACKLIST_DOMAINS = {
    'home.blog', 'livepositively.com', 'blog-planet.com', 'guestpostgenie.com',
    'techdigitalgroups.com', 'slideshare.net', 'blogspot.com', 'wixsite.com',
    'weebly.com', 'freeforums.net', 'forumer.com', 'studiopress.com',
    'wordpress.com', 'wix.com', 'squarespace.com', 'webflow.io',
}


# ============================================================================
# LOGGING
# ============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ============================================================================
# EMAIL EXTRACTION
# ============================================================================

def extract_emails(text: str) -> list:
    """Extract valid-looking emails from text, filtered by blacklist."""
    raw = EMAIL_RE.findall(text)
    cleaned = []
    for e in raw:
        e_lower = e.lower()
        # Skip forbidden patterns
        if FORBIDDEN.search(e):
            continue
        # Skip known useless addresses
        if any(b in e_lower for b in BLACKLIST_EMAILS):
            continue
        # Skip common disposable/placeholder domains
        domain = e_lower.split('@')[1] if '@' in e_lower else ''
        if any(b in domain for b in BLACKLIST_DOMAINS):
            continue
        if len(domain) < 4 or domain.startswith('example'):
            continue
        cleaned.append(e)
    return list(dict.fromkeys(cleaned))  # dedupe preserve order


def clean_email(email: str) -> str:
    """Basic validation + cleaning."""
    email = email.strip().lower()
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return ''
    return email


# ============================================================================
# FIRECRAWL SCRAPE
# ============================================================================

def scrape_firecrawl(url: str, retries: int = 1) -> list:
    """Scrape emails from a URL using Firecrawl."""
    if not HAS_FIRECRAWL:
        return []

    for attempt in range(retries):
        try:
            app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
            result = app.scrape_url(
                url,
                formats=['markdown', 'text'],
                timeout=20000,
            )
            texts = []
            if result and isinstance(result, dict):
                for key in ('markdown', 'text', 'content'):
                    val = result.get(key, '')
                    if val:
                        texts.append(str(val))
            email_list = extract_emails('\n'.join(texts))
            if email_list:
                return email_list
        except Exception as e:
            log(f"    Firecrawl error {url}: {e}")
            time.sleep(2)
    return []


# ============================================================================
# CURL FALLBACK
# ============================================================================

def scrape_curl(url: str) -> list:
    """Fallback scrape using curl + grep."""
    try:
        result = subprocess.run(
            ['curl', '-sL', '--max-time', '15', '-L', url],
            capture_output=True, text=True, timeout=20
        )
        return extract_emails(result.stdout + result.stderr)
    except Exception as e:
        return []


# ============================================================================
# CONTACT PAGE INFERENCE
# ============================================================================

def contact_url(base_url: str) -> str | None:
    """Infer likely contact/about page URLs from a base domain."""
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    domain = parsed.netloc
    paths = [
        '/contact',
        '/contact-us',
        '/about',
        '/about-us',
        '/guest-post',
        '/guest-posts',
        '/write-for-us',
        '/write-for-me',
        '/submit-post',
        '/submit-guest-post',
    ]
    results = []
    for path in paths:
        results.append(f"{parsed.scheme}://{domain}{path}")
    return results


# ============================================================================
# MAIN SCRAPE
# ============================================================================

def main():
    log("=== Contact Page Email Scraper ===")

    # Load DB
    with open(DB_FILE) as f:
        db = json.load(f)
    prospects = db.get('prospects', {})

    # Filter to prospects missing email
    needs_scrape = []
    for url, data in prospects.items():
        email = data.get('email', '').strip()
        if email and email not in ('', 'None', 'null', 'elements@2x.png'):
            continue
        # Also skip bad domains
        url_lower = url.lower()
        if any(b in url_lower for b in BLACKLIST_DOMAINS):
            log(f"  SKIP (bad domain): {url[:80]}")
            continue
        needs_scrape.append((url, data))

    log(f"Need to scrape: {len(needs_scrape)} / {len(prospects)} prospects")
    print()

    scraped = {}
    already_loaded = {}
    if OUTPUT.exists():
        already_loaded = json.loads(OUTPUT.read_text())

    for i, (url, data) in enumerate(needs_scrape, 1):
        domain = data.get('domain', url)
        status = data.get('status', 'unknown')
        score = data.get('score', 0)

        log(f"[{i}/{len(needs_scrape)}] {domain} (score={score}, status={status})")
        log(f"    URL: {url[:100]}")

        emails_found = []

        # 1. Try scraping the write-for-us page directly
        if url and url not in ('', 'None'):
            if HAS_FIRECRAWL:
                emails_found = scrape_firecrawl(url)
                if not emails_found:
                    emails_found = scrape_curl(url)
            else:
                emails_found = scrape_curl(url)

        # 2. If no emails, try inferring contact/about pages
        if not emails_found:
            contact_pages = contact_url(url)
            for cp in contact_pages[:4]:  # try up to 4
                log(f"    Trying: {cp}")
                if HAS_FIRECRAWL:
                    emails_found = scrape_firecrawl(cp)
                    if emails_found:
                        break
                else:
                    emails_found = scrape_curl(cp)
                    if emails_found:
                        break

        if emails_found:
            primary = emails_found[0]
            log(f"    ✅ Found: {emails_found}")
            scraped[url] = {
                'url': url,
                'domain': domain,
                'emails': emails_found,
                'primary_email': primary,
                'scraped_at': datetime.now().isoformat(),
            }
        else:
            log(f"    ❌ No email found")
            scraped[url] = {
                'url': url,
                'domain': domain,
                'emails': [],
                'primary_email': '',
                'scraped_at': datetime.now().isoformat(),
            }

        # Rate limit
        time.sleep(1.5)

        # Save partial progress every 10
        if i % 10 == 0:
            with open(OUTPUT, "w") as f:
                json.dump(scraped, f, indent=2)
            log(f"  → Progress saved ({i}/{len(needs_scrape)})")

    # Final save
    with open(OUTPUT, "w") as f:
        json.dump(scraped, f, indent=2)

    # Report
    found = {k: v for k, v in scraped.items() if v['emails']}
    log(f"\n=== Done. Scraped: {len(scraped)}, Found emails: {len(found)} ===")

    # Merge into DB
    merged = 0
    for url, info in found.items():
        if url in prospects and info['primary_email']:
            if not prospects[url].get('email'):
                prospects[url]['email'] = info['primary_email']
                merged += 1

    if merged:
        with open(DB_FILE, "w") as f:
            json.dump(db, f, indent=2)
        log(f"Merged {merged} new emails into prospect_db.json")

    log(f"\nResults saved to: {OUTPUT}")


if __name__ == '__main__':
    main()
