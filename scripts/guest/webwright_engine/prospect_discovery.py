#!/usr/bin/env python3
"""
Webwright Guest Post Contact Discovery
Fast, timeout-hardened contact page discovery using Firefox.
Run standalone: python3 prospect_discovery.py --url <url>
Run batch: python3 prospect_discovery.py --batch --limit 10
"""
import re
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PROSPECTS_FILE = Path.home() / ".openclaw/workspace/rankbuilder/prospects/guest_prospects.jsonl"
OUT_DIR = Path(__file__).parent

# Priority paths for guest-post/contact pages
PATHS_TO_TRY = [
    "/write-for-us",
    "/submit-guest-post",
    "/guest-post-guidelines",
    "/contact",
    "/about",
    "/contact-us",
    "/contribute",
    "/authors",
    "/team",
    "/become-a-writer",
]


def extract_emails(text: str) -> list:
    """Deduplicated email extraction."""
    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    noise = {"noreply", "no-reply", "example", "test", "admin", "webmaster",
             "hostmaster", "postmaster", "donotreply", "privacy"}
    return list({e for e in found if not any(n in e.lower() for n in noise)})


def discover(url: str) -> dict:
    """Discover contact emails on a URL using Firefox."""
    result = {
        "url": url,
        "emails": [],
        "pages_checked": [],
        "status": "pending"
    }

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 1800},
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )
        # Hard timeout per page — fast sites respond in <3s
        page.set_default_timeout(10000)

        base = url.rstrip("/")

        for path in PATHS_TO_TRY:
            try:
                page.goto(base + path, wait_until="commit", timeout=10000)
                page.wait_for_timeout(1500)  # Brief settle for JS-heavy pages

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

            except Exception:
                result["pages_checked"].append({
                    "path": path,
                    "status": "timeout/error",
                    "emails_found": 0
                })

        result["emails"] = list(set(result["emails"]))
        result["status"] = "complete"
        browser.close()

    return result


def run_batch(limit: int = 10, verbose: bool = True):
    """Run discovery on prospects missing contact emails."""
    prospects = [json.loads(l) for l in PROSPECTS_FILE.read_text().splitlines() if l.strip()]
    missing = [p for p in prospects if not p.get("contact_email")][:limit]

    if verbose:
        print(f"🔍 Checking {len(missing)} prospects for contact emails...\n")

    for p in missing:
        url = p.get("url", "")
        da = p.get("da_estimate", "?")
        if verbose:
            print(f"DA {da} | {url}", end=" ... ", flush=True)

        r = discover(url)

        # Update prospect record
        p["contact_email"] = r["emails"][0] if r["emails"] else "not_found"
        p["discovery_status"] = r["status"]
        p["pages_checked"] = r["pages_checked"]
        p["all_emails"] = r["emails"]

        if verbose:
            status = "✅" if r["emails"] else "⚠️"
            print(f"{status} {r['emails'] or 'no emails'}")

    # Save updated prospects
    PROSPECTS_FILE.write_text("\n".join(json.dumps(p) for p in prospects) + "\n")

    found = sum(1 for p in missing if p.get("contact_email") not in (None, "", "not_found"))
    if verbose:
        print(f"\n✅ Found {found}/{len(missing)} contact emails")


def run_from_urls_file(filepath: Path, verbose: bool = True):
    """Run discovery on URLs listed in a file (one per line)."""
    urls = [u.strip() for u in filepath.read_text().splitlines() if u.strip()]
    if verbose:
        print(f"🔍 Webwright discovery for {len(urls)} URLs from file...")

    found_count = 0
    for url in urls:
        if verbose:
            print(f"  🔍 {url}", end=" ... ", flush=True)
        r = discover(url)
        status = "✅" if r["emails"] else "⚠️"
        if verbose:
            print(f"{status} {r['emails'] or 'no emails'}")
        if r["emails"]:
            found_count += 1

    if verbose:
        print(f"\n✅ Found {found_count}/{len(urls)} contact emails")
    return found_count


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
        r = discover(args.url)
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
            r = discover(missing[0]["url"])
            print(f"Demo: {missing[0]['url']}")
            print(f"  Emails: {r['emails']}")
            print(f"  Status: {r['status']}")
        else:
            print("All prospects have contact emails!")


if __name__ == "__main__":
    main()