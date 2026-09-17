#!/usr/bin/env python3
"""
FortressBlinds Competitor Intel — powered by DeepAPI.
Tracks SA shutter/blinds competitors: scrapes their sites, checks keyword
overlap, and generates a weekly intel report.

Usage:
    python deepapi_competitors.py scrape      # Scrape competitor sites
    python deepapi_competitors.py report      # Generate markdown report
    python deepapi_competitors.py run         # Scrape + report
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import scrape_website, seo_competitors, get_balance

# SA security shutter/blinds competitors
COMPETITORS = [
    {"name": "American Shutters", "url": "https://www.americanshutters.co.za/"},
    {"name": "Custom Blinds", "url": "https://customblinds.co.za/"},
    {"name": "Aesthetics Shutters", "url": "https://aestheticsshutters.co.za/"},
    {"name": "Artilux", "url": "https://artilux.com.au/"},  # reference
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rankings", "competitor_intel.json")
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rankings", "competitor-intel.md")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"competitors": {}, "updated_at": None}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["updated_at"] = datetime.now().astimezone().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def cmd_scrape():
    print(f"🔍 Scraping {len(COMPETITORS)} competitors | Balance: ${get_balance():.2f}")
    state = load_state()
    total_cost = 0
    for comp in COMPETITORS:
        print(f"  {comp['name']}: {comp['url']}")
        try:
            result = scrape_website(comp["url"], max_chars=3000, max_pages=3, max_cost_usd="0.10")
            cost = result.get("debitMicrousd") or 0
            total_cost += cost
            out = result.get("output")
            pages = out if isinstance(out, list) else []
            # Extract key content
            page_text = ""
            for p in pages[:2]:
                page_text += (p.get("markdown") or p.get("text") or "")[:1500] + "\n"
            state["competitors"][comp["name"]] = {
                "url": comp["url"],
                "scraped_at": datetime.now().astimezone().isoformat(),
                "cost_microusd": cost,
                "content_preview": page_text[:2000],
                "pages_count": len(pages),
            }
        except Exception as e:
            print(f"    ERROR: {e}")
        # Brief pause
        import time
        time.sleep(1)

    save_state(state)
    print(f"\n✅ Scraped {len(state['competitors'])} competitors (cost ${total_cost/1e6:.4f})")
    print(f"Balance: ${get_balance():.2f}")
    return state


def cmd_report():
    state = load_state()
    lines = [
        "# FortressBlinds Competitor Intel (DeepAPI)",
        f"**Updated:** {state.get('updated_at', 'never')}",
        f"**DeepAPI balance:** ${get_balance():.2f}",
        "",
    ]
    for name, data in state.get("competitors", {}).items():
        lines.append(f"## {name}")
        lines.append(f"- **URL:** {data.get('url')}")
        lines.append(f"- **Scraped:** {data.get('scraped_at', '?')[:16]}")
        lines.append(f"- **Pages:** {data.get('pages_count')}")
        preview = data.get("content_preview", "")
        lines.append("")
        lines.append("**Content preview:**")
        lines.append("")
        lines.append("> " + preview.replace("\n", " ")[:500])
        lines.append("")
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✅ Report written to {REPORT_FILE}")
    print("\n".join(lines)[:1500])


def cmd_run():
    cmd_scrape()
    print()
    cmd_report()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "scrape":
        cmd_scrape()
    elif cmd == "report":
        cmd_report()
    elif cmd == "run":
        cmd_run()
    else:
        print(__doc__)
