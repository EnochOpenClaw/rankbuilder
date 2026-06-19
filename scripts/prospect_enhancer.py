#!/usr/bin/env python3
"""
prospect_enhancer.py — DA scoring, domain quality filter, and DB enrichment.
Adds Domain Authority (MOZ free API), quality flags, and applies domain
filters to clean up the prospect DB before outreach.

Usage:
    python3 prospect_enhancer.py          # Full run: DA check + quality filter
    python3 prospect_enhancer.py --score  # Score existing prospects only
    python3 prospect_enhancer.py --filter # Apply domain filter only (no API calls)
    python3 prospect_enhancer.py --report # Print quality report without writing
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

DB_FILE    = Path(__file__).parent.parent / 'prospects' / 'prospect_db.json'
LOG_FILE   = Path(__file__).parent / 'logs' / 'prospect_enhancer.log'
OUTPUT     = Path(__file__).parent.parent / 'prospects' / 'prospect_db_enhanced.json'

# Quality thresholds
MIN_DA            = 15      # Minimum DA to pitch (tier 2+)
MIN_SCORE         = 45      # Minimum prospect score
ALLOWED_TLDS      = {'.com', '.org', '.net', '.co', '.io', '.edu', '.gov',
                     '.co.uk', '.co.za', '.co.nz', '.com.au', '.ca'}
# TLDs that are always bad / free platforms
BLOCKED_TLDS      = {'.blog', '.home.blog', '.livepositively.com',
                     '.blogspot.com', '.wixsite.com', '.weebly.com',
                     '.wordpress.com', '.squarespace.com', '.wix.com',
                     '.webflow.io', '.site123.com', '.webnode.com',
                     '.freeforums.net', '.forumer.com', '.proboards.com'}
# Known bad/weak domain patterns (exact or substring)
BLOCKED_DOMAINS   = {
    'home.blog', 'livepositively.com', 'blog-planet.com', 'guestpostgenie.com',
    'techdigitalgroups.com', 'slideshare.net', 'blogspot.com', 'wixsite.com',
    'weebly.com', 'freeforums.net', 'forumer.com', 'studiopress.com',
    'wordpress.com', 'wix.com', 'squarespace.com', 'webflow.io',
    'webkul.com', 'blogtt.org', 'guestpostgenie', 'blog-planet',
    'sky.blog', 'luxury.blog', 'tech.blog', 'love.blog', 'best.blog',
    'infinity.freeforums', 'vacationforum.com',
}
# Free/Guest-post-mill domains
GUEST_POST_MILLS = {
    'guestpostgenie.com', 'blog-planet.com', 'guestpostbloga', 'guestpostblogb',
    'guestpost', 'linkpublishers.com', 'nicheguestpost.com', 'rocketguestposting.com',
    'guestposting website', 'guestpostingservice', 'guestpostnetwork',
    'qualityguestpost', 'backlinks34', 'fastguestpost', 'guestpostplace',
}


# ============================================================================
# LOGGING
# ============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ============================================================================
# DOMAIN EXTRACTION & VALIDATION
# ============================================================================

def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    if not url:
        return ''
    url = url.strip().lower()
    # Remove protocol
    url = re.sub(r'^https?://', '', url)
    # Remove path/query
    url = url.split('/')[0]
    # Remove www.
    url = re.sub(r'^www\.', '', url)
    return url


def get_tld(domain: str) -> str:
    """Get the TLD of a domain."""
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.' + '.'.join(parts[-2:])
    if parts:
        return '.' + parts[-1]
    return ''


def is_blocked_domain(url: str, domain: str = '') -> tuple:
    """Check if domain is blocked. Returns (blocked: bool, reason: str)."""
    if not domain:
        domain = extract_domain(url)
    domain_lower = domain.lower()

    # Exact blocked domains
    if domain_lower in BLOCKED_DOMAINS:
        return True, 'blocked_domain_exact'

    # Substring blocked
    for blocked in BLOCKED_DOMAINS:
        if blocked in domain_lower:
            return True, 'blocked_domain_substring'

    # Blocked TLDs
    tld = get_tld(domain_lower)
    if tld in BLOCKED_TLDS:
        return True, f'blocked_tld:{tld}'

    # Guest post mills
    for mill in GUEST_POST_MILLS:
        if mill in domain_lower:
            return True, 'guest_post_mill'

    return False, ''


def is_quality_domain(domain: str) -> bool:
    """Basic quality check without API call."""
    tld = get_tld(domain.lower())

    # Must have a known commercial/org TLD
    if tld not in ALLOWED_TLDS:
        return False
    return True


# ============================================================================
# DA SCORING (MOZ Free API — leastcors.io proxy)
# ============================================================================

# MOZ has a free API (10k rows/month). We'll try it.
# Endpoint: https://lsapi.seomoz.com/v2/linkscape/url-metrics
# Alternative: use a simple link-index check via thefree SEO API

# We'll implement a multi-strategy approach:
# 1. Try MOZ free API
# 2. Fall back to scraped DA from existing DB (if any)
# 3. Fall back to proxy metric based on link profile heuristics

MOZ_API_KEY = ''  # User should add their free MOZ API key here
              # Get it free at: https://moz.com/products/api/lite
              # We implement the structure but won't call without a key


def score_da_moz(domain: str) -> int | None:
    """
    Get DA via MOZ free API.
    Returns DA (0-100) or None if unavailable.
    Rate limit: 10k URL metrics/month on free tier.
    """
    if not MOZ_API_KEY:
        return None

    import urllib.request, urllib.error

    url = 'https://lsapi.seomoz.com/v2/linkscape/url-metrics'
    payload = json.dumps({
        "targets": [f"https://{domain}"],
        "metrics": ["da", "upa", "pda"],
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MOZ_API_KEY}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get('results'):
                return int(data['results'][0].get('da', 0))
    except Exception:
        pass
    return None


def score_domain_heuristic(domain: str, url: str = '') -> int:
    """
    Heuristic DA estimate based on domain signals.
    Used when no MOZ API key is available.
    """
    domain_lower = domain.lower()
    score = 30  # baseline

    # Strong positive signals
    if any(ext in domain_lower for ext in ['.edu', '.gov', '.co.uk', '.com.au', '.co.za']):
        score += 10
    if 'news' in domain_lower or 'magazine' in domain_lower:
        score += 8
    if 'architect' in domain_lower or 'design' in domain_lower:
        score += 5
    if 'renovat' in domain_lower or 'home' in domain_lower or 'build' in domain_lower:
        score += 5
    if url and '/write-for-us' in url:
        score += 5

    # Strong negative signals
    if any(b in domain_lower for b in ['blog', 'forum', 'guest', 'post', 'link']):
        score -= 10
    if 'shutters' in domain_lower or 'blinds' in domain_lower or 'awning' in domain_lower:
        score += 15  # niche-relevant = bonus
    if any(tld in domain_lower for tld in ['.org', '.net', '.io']):
        score += 3

    return max(5, min(95, score))


# ============================================================================
# MAIN ENHANCEMENT
# ============================================================================

def enhance_prospect(url: str, data: dict, use_api: bool = False) -> dict:
    """Enhance a single prospect with DA, quality flags, and corrections."""
    domain = data.get('domain') or extract_domain(url)
    enhanced = dict(data)

    # 1. Domain extraction fix
    if not enhanced.get('domain'):
        enhanced['domain'] = domain

    # 2. Blocklist check
    blocked, reason = is_blocked_domain(url, domain)
    enhanced['blocked'] = blocked
    enhanced['block_reason'] = reason

    # 3. Quality flags
    enhanced['quality_tld'] = is_quality_domain(domain)
    enhanced['tld'] = get_tld(domain)

    # 4. DA scoring
    da = None
    if use_api and MOZ_API_KEY:
        da = score_da_moz(domain)
    if da is None:
        da = score_domain_heuristic(domain, url)
    enhanced['da'] = da

    # 5. Combined quality score (0-100)
    base_score = data.get('score', 50)
    da_bonus = int((da or 0) / 5) if da else 0
    quality_score = min(100, base_score + da_bonus)
    enhanced['quality_score'] = quality_score

    # 6. Pitch recommendation
    if blocked:
        enhanced['pitch'] = 'BLOCKED'
    elif quality_score < MIN_SCORE and not data.get('email'):
        enhanced['pitch'] = 'LOW_PRIORITY'
    elif da and da < MIN_DA:
        enhanced['pitch'] = 'BELOW_DA_THRESHOLD'
    elif enhanced.get('email'):
        enhanced['pitch'] = 'READY'
    else:
        enhanced['pitch'] = 'NEEDS_EMAIL'

    return enhanced


def main():
    parser = argparse.ArgumentParser(description='Enhance prospect DB with DA scores + quality filters')
    parser.add_argument('--score', action='store_true', help='Score prospects (no filter)')
    parser.add_argument('--filter', action='store_true', help='Apply domain filter only')
    parser.add_argument('--report', action='store_true', help='Print quality report only (no writes)')
    parser.add_argument('--da-key', type=str, default='', help='MOZ free API key for real DA')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without writing')
    args = parser.parse_args()

    global MOZ_API_KEY
    if args.da_key:
        MOZ_API_KEY = args.da_key

    log("=== Prospect Enhancer Run ===")

    with open(DB_FILE) as f:
        db = json.load(f)
    prospects = db.get('prospects', {})

    log(f"Loaded {len(prospects)} prospects")

    # Enhancement pass
    enhanced_prospects = {}
    stats = {
        'total': len(prospects),
        'blocked': 0,
        'needs_email': 0,
        'below_da': 0,
        'low_priority': 0,
        'ready': 0,
        'has_da_real': 0,
        'da_none': 0,
        'no_email': 0,
    }

    for url, data in prospects.items():
        enh = enhance_prospect(url, data, use_api=bool(MOZ_API_KEY))
        enhanced_prospects[url] = enh

        pitch = enh.get('pitch', '?')
        stats[pitch.lower()] = stats.get(pitch.lower(), 0) + 1
        stats[pitch.lower().replace(' ', '_')]

        if enh.get('blocked'):
            stats['blocked'] += 1
        if not enh.get('email'):
            stats['no_email'] += 1

        if args.report:
            reason = ''
            if enh.get('blocked'):
                reason = f" [BLOCKED: {enh.get('block_reason')}]"
            elif enh.get('pitch') == 'NEEDS_EMAIL':
                reason = ' [needs email]'
            elif enh.get('pitch') == 'READY':
                reason = ' ✅'
            print(f"  score={enh.get('quality_score',0):3d} da={enh.get('da','?'):>3} | {enh.get('domain',url)[:50]:50s} | {reason}")

    # Print report
    print("\n=== Quality Report ===")
    print(f"Total prospects:  {stats['total']}")
    print(f"Blocked:          {stats['blocked']} ({stats['blocked']/stats['total']*100:.0f}%)")
    print(f"No email:         {stats['no_email']}")
    print(f"Ready to pitch:   {stats.get('ready', 0)}")
    print(f"Needs email:      {stats.get('needs_email', 0)}")
    print(f"Below DA thresh:  {stats.get('below_da_threshold', 0)}")
    print(f"Low priority:     {stats.get('low_priority', 0)}")
    print()

    # Apply filter if requested
    if args.filter and not args.report and not args.dry_run:
        original_count = len(enhanced_prospects)
        filtered = {
            url: data for url, data in enhanced_prospects.items()
            if not data.get('blocked') and data.get('pitch') != 'LOW_PRIORITY'
        }
        removed = original_count - len(filtered)
        log(f"Filtered {removed} blocked/low-priority prospects → {len(filtered)} remain")
        enhanced_prospects = filtered

    # Write output
    if not args.report and not args.dry_run:
        db['prospects'] = enhanced_prospects
        db['last_enhanced'] = datetime.now().isoformat()
        db['enhanced_by'] = 'prospect_enhancer.py'

        # Backup original
        backup = DB_FILE.with_suffix('.json.bak')
        with open(backup, 'w') as f:
            json.dump(json.loads(Path(DB_FILE).read_text()), f, indent=2)
        log(f"Backed up original to {backup.name}")

        with open(DB_FILE, 'w') as f:
            json.dump(db, f, indent=2)
        log(f"Written {len(enhanced_prospects)} enhanced prospects to prospect_db.json")

    elif args.dry_run:
        print("Dry run — no files written")


if __name__ == '__main__':
    main()
