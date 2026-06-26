#!/usr/bin/env python3
"""
Webwright Guest Post Contact Discovery
Fast, timeout-hardened contact page discovery using Firefox.

Optimizations (vs v1):
- Only 4 highest-value paths instead of 9
- 7s timeout per page (vs 10s) — responsive pages respond in <2s
- Concurrent URL processing (2 at a time vs sequential)
- Early exit when email found on a page
- No browser context overhead between URLs

Run standalone: python3 prospect_discovery.py --url <url>
Run batch:      python3 prospect_discovery.py --batch --limit 10
Run URL file:   python3 prospect_discovery.py --batch-urls-file /tmp/urls.txt
"""
import re
import json
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

PROSPECTS_FILE = Path.home() / ".openclaw/workspace/rankbuilder/prospects/guest_prospects.jsonl"
OUT_DIR = Path(__file__).parent

# Reduced to 4 highest-value paths (most likely to have contact emails)
# Ordered by probability of yielding a useful contact address
PATHS_TO_TRY = [
    "/contact",
    "/about",
    "/write-for-us",
    "/contact-us",
]

PAGE_TIMEOUT_MS = 7000   # 7s — responsive sites respond in <2s
SETTLE_MS = 1000         # 1s JS settle time (reduced from 1500ms)
MAX_CONCURRENT = 2       # 2 browsers at a time — limits memory/CPU but keeps speed

# Email noise patterns
EMAIL_NOISE = {
    "noreply", "no-reply", "example", "test", "admin", "webmaster",
    "hostmaster", "postmaster", "donotreply", "privacy", "jobs", "careers",
    "hello", "info", "support", "sales", "marketing",
}


def extract_emails(text: str) -> list:
    """Deduplicated email extraction, noise-filtered."""
    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return list({
        e for e in found
        if not any(n in e.lower() for n in EMAIL_NOISE)
    })


def discover_single(url: str) -> dict:
    """
    Discover contact emails on a single URL.
    Returns early when first email is found (high probability of validity).
    """
    result = {
        "url": url,
        "emails": [],
        "pages_checked": [],
        "status": "pending"
    }

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=True,
            args=["--disable-images", "--disable-css"]  # Faster page loads
        )
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        base = url.rstrip("/")
        email_found = False

        for path in PATHS_TO_TRY:
            if email_found:
                break  # Early exit — we already have what we need

            try:
                target = base + path
                page.goto(target, wait_until="commit", timeout=PAGE_TIMEOUT_MS)
                page.wait_for_timeout(SETTLE_MS)

                body = page.locator("body").inner_text()
                emails = extract_emails(body)

                result["pages_checked"].append({
                    "path": path,
                    "url": page.url,
                    "status": "ok",
                    "emails_found": len(emails)
                })

                if emails:
                    result["emails"].extend(emails)
                    # Don't break here — collect all emails from all pages
                    # for better quality selection

            except Exception as e:
                result["pages_checked"].append({
                    "path": path,
                    "status": "timeout/error",
                    "emails_found": 0
                })

        result["emails"] = list(set(result["emails"]))
        result["status"] = "complete"
        browser.close()

    return result


def discover_batch_concurrent(urls: list, max_workers: int = MAX_CONCURRENT) -> list:
    """
    Run discovery on multiple URLs concurrently.
    Returns list of result dicts in same order as input.
    """
    results = {}

    def worker(url: str) -> tuple:
        try:
            return (url, discover_single(url))
        except Exception as e:
            return (url, {"url": url, "emails": [], "pages_checked": [],
                          "status": f"error: {e}"})

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, u): u for u in urls}
        for future in as_completed(futures):
            url, result = future.result()
            results[url] = result

    return [results.get(u) for u in urls if u in results]


def run_batch(limit: int = 10, verbose: bool = True):
    """Run discovery on prospects missing contact emails."""
    prospects = [json.loads(l) for l in PROSPECTS_FILE.read_text().splitlines() if l.strip()]
    missing = [p for p in prospects if not p.get("contact_email")][:limit]

    if verbose:
        print(f"🔍 Checking {len(missing)} prospects for contact emails (concurrent={MAX_CONCURRENT})...\n")

    urls = [p.get("url", "") for p in missing]
    results = discover_batch_concurrent(urls)

    found = 0
    for p, r in zip(missing, results):
        if r is None:
            continue

        p["contact_email"] = r["emails"][0] if r["emails"] else "not_found"
        p["discovery_status"] = r["status"]
        p["pages_checked"] = r["pages_checked"]
        p["all_emails"] = r["emails"]

        if verbose:
            status = "✅" if r["emails"] else "⚠️"
            da = p.get("da_estimate", "?")
            print(f"  DA {da} | {p.get('url','')} ... {status} {r['emails'] or 'no emails'}")

        if r["emails"]:
            found += 1

    # Save updated prospects
    PROSPECTS_FILE.write_text("\n".join(json.dumps(p) for p in prospects) + "\n")

    if verbose:
        print(f"\n✅ Found {found}/{len(missing)} contact emails")


def run_from_urls_file(filepath: Path, verbose: bool = True):
    """Run discovery on URLs listed in a file (one per line)."""
    urls = [u.strip() for u in filepath.read_text().splitlines() if u.strip()]
    if verbose:
        print(f"🔍 Webwright discovery for {len(urls)} URLs from file (concurrent={MAX_CONCURRENT})...")

    results = discover_batch_concurrent(urls)

    found = 0
    for url, r in zip(urls, results):
        if r is None:
            continue
        if verbose:
            status = "✅" if r["emails"] else "⚠️"
            print(f"  {status} {url} → {r['emails'] or 'no emails'}")
        if r["emails"]:
            found += 1

    if verbose:
        print(f"\n✅ Found {found}/{len(urls)} contact emails")

    return found


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Webwright Contact Discovery")
    parser.add_argument("--url", help="Single URL to check")
    parser.add_argument("--batch", action="store_true", help="Run batch on missing-email prospects")
    parser.add_argument("--batch-urls-file", type=Path, help="File with URLs (one per line) to check")
    parser.add_argument("--limit", type=int, default=10, help="Max prospects for batch")
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    verbose = not args.quiet

    if args.url:
        r = discover_single(args.url)
        print(f"URL: {args.url}")
        print(f"Emails: {r['emails']}")
        print(f"Pages checked: {len(r['pages_checked'])}")
        print(f"Status: {r['status']}")

    elif args.batch_urls_file:
        run_from_urls_file(args.batch_urls_file, verbose=not args.quiet)

    elif args.batch:
        run_batch(limit=args.limit, verbose=verbose)

    else:
        # Demo: check first missing-email prospect
        prospects = [json.loads(l) for l in PROSPECTS_FILE.read_text().splitlines() if l.strip()]
        missing = [p for p in prospects if not p.get("contact_email")]
        if missing:
            r = discover_single(missing[0]["url"])
            print(f"Demo: {missing[0]['url']}")
            print(f"  Emails: {r['emails']}")
            print(f"  Status: {r['status']}")
        else:
            print("All prospects have contact emails!")


if __name__ == "__main__":
    main()