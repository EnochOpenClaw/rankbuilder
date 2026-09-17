#!/usr/bin/env python3
"""
FortressBlinds SEO Tracker — powered by DeepAPI.
Tracks keyword rankings + does keyword research for fortressblinds.co.za.

Usage:
    python deepapi_seo.py keyword-research     # Research target keywords
    python deepapi_seo.py rank <keyword>       # Check rank for a keyword
    python deepapi_seo.py rank-all             # Check all tracked keywords
    python deepapi_seo.py report               # Generate markdown report
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import seo_keywords, seo_rank, get_balance

DOMAIN = "fortressblinds.co.za"

# Core target keywords for FortressBlinds
TRACKED_KEYWORDS = [
    "security shutters south africa",
    "aluminium shutters johannesburg",
    "fly screens south africa",
    "security screens south africa",
    "shutters johannesburg",
    "home security shutters",
    "burglar proofing johannesburg",
    "window security screens",
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rankings", "fortressblinds_deepapi_state.json")
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rankings", "fortressblinds-seo-deepapi.md")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"keywords": {}, "updated_at": None}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["updated_at"] = datetime.now().astimezone().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def cmd_keyword_research():
    print(f"🔍 Keyword research for {DOMAIN}...")
    print(f"Balance: ${get_balance():.2f}")
    result = seo_keywords(TRACKED_KEYWORDS)
    print(f"Status: {result.get('status')} | Cost: {result.get('debitMicrousd')} micro-USD")
    out = result.get("output") or {}
    keywords = out.get("keywords") or out.get("results") or []
    if not keywords and isinstance(out, dict):
        # Try to find keyword data in output
        keywords = out.get("data") or []
    for kw in keywords[:10]:
        if isinstance(kw, dict):
            print(f"  {kw.get('keyword','?')}: vol={kw.get('volume') or kw.get('monthlySearches') or '?'} diff={kw.get('difficulty') or kw.get('keywordDifficulty') or '?'} intent={kw.get('intent') or '?'}")
    print("Done. See full output in state file.")
    return result


def cmd_rank(keyword):
    print(f"📈 Checking rank for '{keyword}' on {DOMAIN}...")
    result = seo_rank(DOMAIN, keyword)
    print(f"Status: {result.get('status')} | Cost: {result.get('debitMicrousd')} micro-USD")
    out = result.get("output") or {}
    print(json.dumps(out, indent=2)[:600] if out else "No output")
    return result


def cmd_rank_all():
    print(f"📊 Checking rankings for {len(TRACKED_KEYWORDS)} keywords on {DOMAIN}...")
    state = load_state()
    total_cost = 0
    for kw in TRACKED_KEYWORDS:
        result = seo_rank(DOMAIN, kw)
        cost = result.get("debitMicrousd") or 0
        total_cost += cost
        out = result.get("output") or {}
        rank = out.get("position")  # null means not in top 10
        if rank is None:
            rank = out.get("rank") or "Not in top 10"
        else:
            rank = str(rank)
        # Store in state
        state["keywords"].setdefault(kw, {})
        state["keywords"][kw]["rank"] = rank
        state["keywords"][kw]["checked_at"] = datetime.now().astimezone().isoformat()
        print(f"  '{kw}': rank={rank} (cost {cost} micro-USD)")
    save_state(state)
    print(f"\nTotal cost: {total_cost} micro-USD (${total_cost/1e6:.4f})")
    print(f"Balance after: ${get_balance():.2f}")
    return state


def cmd_report():
    state = load_state()
    lines = [
        f"# FortressBlinds SEO Rankings (DeepAPI)",
        f"**Updated:** {state.get('updated_at', 'never')}",
        f"**Domain:** {DOMAIN}",
        f"**DeepAPI balance:** ${get_balance():.2f}",
        "",
        "| Keyword | Rank | Checked |",
        "|---------|------|---------|",
    ]
    for kw, data in state.get("keywords", {}).items():
        lines.append(f"| {kw} | {data.get('rank', '?')} | {data.get('checked_at', '?')[:16]} |")
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✅ Report written to {REPORT_FILE}")
    print("\n".join(lines))


def cmd_scheduled_run():
    """Full scheduled run: rank-all + report. Prints summary for cron delivery."""
    state = cmd_rank_all()
    print()
    # Summarize
    ranked = [kw for kw, d in state.get("keywords", {}).items() if isinstance(d.get("rank"), str) and d["rank"].isdigit()]
    print(f"Summary: {len(ranked)} of {len(state.get('keywords', {}))} keywords ranked in top 10")
    for kw in ranked:
        print(f"  🏆 {kw}: #{state['keywords'][kw]['rank']}")
    cmd_report()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "keyword-research":
        cmd_keyword_research()
    elif cmd == "rank" and len(sys.argv) >= 3:
        cmd_rank(sys.argv[2])
    elif cmd == "rank-all":
        cmd_rank_all()
    elif cmd == "scheduled-run":
        cmd_scheduled_run()
    elif cmd == "report":
        cmd_report()
    else:
        print(__doc__)
