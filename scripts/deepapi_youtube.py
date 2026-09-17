#!/usr/bin/env python3
"""
FortressBlinds YouTube Content Discovery — powered by DeepAPI.
Searches YouTube for target keywords to find content gaps, top-ranking videos,
and competitor videos in the security shutters/blinds niche.

Usage:
    python deepapi_youtube.py          # Run discovery, print results
    python deepapi_youtube.py --save   # Save results to state file
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import call, get_balance

# Target YouTube keywords for FortressBlinds content strategy
KEYWORDS = [
    "security shutters south africa",
    "aluminium shutters installation",
    "how to measure for security shutters",
    "security screens home protection",
    "fly screens south africa",
    "plantation shutters south africa",
    "home security window protection",
    "outdoor blinds patio",
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "deepapi_youtube.json")


def search_youtube(query, max_items=5):
    result = call("/v1/scrape/youtube/search", {"query": query, "maxItems": max_items, "maxCostUsd": "0.10"})
    out = result.get("output")
    if isinstance(out, list):
        vids = out
    elif isinstance(out, dict):
        vids = out.get("videos") or out.get("results") or out.get("items") or []
    else:
        vids = []
    return vids, result.get("debitMicrousd")


def main():
    save = "--save" in sys.argv
    print(f"🎬 YouTube Content Discovery | Balance: ${get_balance():.2f}")
    all_vids = []
    total_cost = 0

    for kw in KEYWORDS:
        print(f"  Searching: '{kw}'")
        vids, cost = search_youtube(kw)
        total_cost += cost or 0
        for v in vids:
            if isinstance(v, dict):
                ch = v.get("channel") or {}
                all_vids.append({
                    "keyword": kw,
                    "title": v.get("title") or "?",
                    "url": v.get("url") or v.get("videoUrl") or "?",
                    "channel": (ch.get("name") if isinstance(ch, dict) else ch) or "?",
                    "views": v.get("views") or v.get("viewCount") or 0,
                    "duration": v.get("duration") or v.get("length") or "?",
                    "published": v.get("publishedAt") or v.get("publishDate") or None,
                })
        time.sleep(1)

    # Dedup by url
    seen = set()
    unique = []
    for v in all_vids:
        u = v["url"]
        if u not in seen:
            seen.add(u)
            unique.append(v)

    print(f"\n✅ Found {len(unique)} unique videos (cost ${total_cost/1e6:.4f})")
    print(f"Balance: ${get_balance():.2f}")

    # Show top videos by views per keyword
    print("\nTop videos by keyword:")
    by_kw = {}
    for v in unique:
        by_kw.setdefault(v["keyword"], []).append(v)
    for kw, vids in by_kw.items():
        vids.sort(key=lambda x: x.get("views") or 0, reverse=True)
        top = vids[0] if vids else None
        if top:
            print(f"  [{kw}] '{top['title'][:50]}' — {top.get('views')} views ({top.get('channel')})")

    if save:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"videos": unique, "updated_at": datetime.now().astimezone().isoformat()}, f, indent=2)
        print(f"\n💾 Saved {len(unique)} videos to {STATE_FILE}")

    return unique


if __name__ == "__main__":
    main()
