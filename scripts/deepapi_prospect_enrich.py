#!/usr/bin/env python3
"""
DeepAPI Prospect Enrichment — powered by DeepAPI.
Enriches RankBuilder prospects with recent news + content topics using
cheap web search ($0.005 each). Optionally uses deep-research for high-value
prospects (--deep flag).

Usage:
    python deepapi_prospect_enrich.py                   # Enrich up to 10 prospects
    python deepapi_prospect_enrich.py --limit 50        # Enrich 50
    python deepapi_prospect_enrich.py --deep            # Use deep-research (pricier)
    python deepapi_prospect_enrich.py --dry             # Dry run, no spend
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import web_search, call, get_balance

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prospects", "prospect_db.json")


def load_db():
    with open(DB_FILE) as f:
        return json.load(f)


def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


def enrich_prospect(domain, deep=False, max_cost="0.05"):
    """Enrich a prospect domain with recent info via DeepAPI."""
    if deep:
        result = call("/v1/research/deep", {
            "query": f"Find recent news, blog topics, and content focus for {domain} (a website in home/outdoor/security niche)",
            "maxCostUsd": "0.30",
        })
    else:
        result = web_search(f"{domain} recent news blog topics", max_results=5, max_cost_usd=max_cost)

    out = result.get("output")
    cost = result.get("debitMicrousd") or 0

    enrichment = {
        "enriched_at": datetime.now().astimezone().isoformat(),
        "method": "deep-research" if deep else "web-search",
        "cost_microusd": cost,
        "summary": "",
        "sources": [],
    }

    if deep:
        if isinstance(out, dict) and out.get("answer"):
            enrichment["summary"] = str(out["answer"])[:800]
    else:
        # Extract search result snippets
        results = out.get("results") or out.get("items") or [] if isinstance(out, dict) else (out if isinstance(out, list) else [])
        snippets = []
        for r in results[:5]:
            if isinstance(r, dict):
                snippets.append({"title": r.get("title", ""), "url": r.get("url", "")})
        enrichment["sources"] = snippets
        enrichment["summary"] = "; ".join([s.get("title", "") for s in snippets])[:500]

    return enrichment, cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="Number of prospects to enrich")
    ap.add_argument("--deep", action="store_true", help="Use deep-research (pricier)")
    ap.add_argument("--dry", action="store_true", help="Dry run — no API calls")
    args = ap.parse_args()

    db = load_db()
    prospects = db.get("prospects", {})
    print(f"🔍 DeepAPI Prospect Enrichment | {len(prospects)} prospects | Balance: ${get_balance():.2f}")

    # Pick prospects not yet enriched
    to_enrich = [d for d, p in prospects.items() if not p.get("enriched_at")][:args.limit]
    print(f"  Enriching {len(to_enrich)} prospects ({'DEEP' if args.deep else 'web-search'} mode)")

    total_cost = 0
    for i, domain in enumerate(to_enrich):
        if args.dry:
            print(f"  [dry] {domain} — would enrich")
            continue
        print(f"  [{i+1}/{len(to_enrich)}] {domain}...")
        try:
            enrichment, cost = enrich_prospect(domain, deep=args.deep)
            prospects[domain].update(enrichment)
            total_cost += cost
            status = "✅" if enrichment["summary"] else "⚠️ no data"
            print(f"    {status} ({len(enrichment['summary'])} chars, ${cost/1e6:.4f})")
        except Exception as e:
            print(f"    ❌ {e}")
        time.sleep(1)

    if not args.dry:
        save_db(db)
        print(f"\n✅ Enriched {len(to_enrich)} prospects (cost ${total_cost/1e6:.4f})")
        print(f"Balance: ${get_balance():.2f}")


if __name__ == "__main__":
    main()
