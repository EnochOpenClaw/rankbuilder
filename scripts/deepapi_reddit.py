#!/usr/bin/env python3
"""
DeepAPI-powered Reddit discovery for RankBuilder.
Uses DeepAPI /v1/scrape/reddit/search instead of the blocked organic Reddit API
or the web_search workaround. Finds relevant posts for FortressBlinds outreach.

Output: JSON list of relevant posts, compatible with reddit_monitor.py consumption.

Usage:
    python deepapi_reddit.py           # Run discovery, print JSON
    python deepapi_reddit.py --save    # Save results to state file
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import call, get_balance

# Target subreddits + queries (subreddit: prefix gives targeted results)
TARGET_SUBREDDITS = [
    "HomeImprovement", "homesecurity", "homedefense",
    "southafrica", "preppers", "DIY", "HomeDecorating",
]

# Base topics to search within each subreddit
TOPICS = [
    "security shutters",
    "aluminium shutters",
    "security screen",
    "burglar proofing",
    "window security",
    "plantation shutters",
    "fly screens",
    "outdoor blinds",
]


def build_queries():
    """Build targeted subreddit+topic queries."""
    queries = []
    for sub in TARGET_SUBREDDITS:
        for topic in TOPICS:
            queries.append(f"subreddit:{sub} {topic}")
    return queries

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "deepapi_reddit_posts.json")


def search_reddit(query, max_items=10):
    """Search Reddit via DeepAPI. Output is a list of post dicts."""
    result = call("/v1/scrape/reddit/search", {
        "query": query,
        "maxItems": max_items,
        "maxCostUsd": "0.15",
    })
    out = result.get("output")
    # Output is a bare list of posts
    if isinstance(out, list):
        posts = out
    elif isinstance(out, dict):
        posts = out.get("posts") or out.get("results") or out.get("items") or []
    else:
        posts = []
    return posts, result.get("debitMicrousd")


# Relevance keywords — posts must relate to shutters/screens/home security
RELEVANT_TERMS = [
    "shutter", "shutters", "screen", "screens", "blind", "blinds",
    "security", "secure", "burglar", "window", "door", "flyscreen",
    "insect", "patio", "aluminium", "aluminum", "home improv",
    "home defense", "protection", "install", "DIY",
]


def is_relevant(post):
    """Filter out posts not related to shutters/screens/home security."""
    text = " ".join([str(post.get("title", "")), str(post.get("text", "") or "")]).lower()
    return any(term in text for term in RELEVANT_TERMS)


def main():
    save = "--save" in sys.argv
    print(f"🔴 DeepAPI Reddit Discovery | Balance: ${get_balance():.2f}")
    all_posts = []
    total_cost = 0

    # Limit: only query a subset of subreddits per run to control cost unless --deep
    queries = build_queries()
    if "--deep" not in sys.argv:
        # Default: 3 subreddits x 3 topics = 9 queries (~$0.20)
        queries = [q for i, q in enumerate(queries) if (i % 2) == 0][:12]

    for query in queries:
        print(f"  Searching: '{query}'")
        posts, cost = search_reddit(query, max_items=5)
        total_cost += cost or 0
        for p in posts:
            if isinstance(p, dict):
                all_posts.append({
                    "query": query,
                    "subreddit": p.get("subreddit") or "?",
                    "title": p.get("title") or "?",
                    "url": p.get("url") or p.get("permalink") or "?",
                    "score": p.get("score") or 0,
                    "num_comments": p.get("comments") or p.get("numComments") or 0,
                    "created_utc": p.get("postedAt") or p.get("createdUtc") or None,
                    "author": p.get("author") or "?",
                    "body": (p.get("text") or p.get("selftext") or p.get("body") or "")[:200],
                })
        time.sleep(1)  # be gentle

    # Dedup by url + filter for relevance
    seen = set()
    unique = []
    for p in all_posts:
        u = p["url"]
        if u in seen:
            continue
        seen.add(u)
        if is_relevant(p):
            unique.append(p)

    print(f"\n✅ Found {len(unique)} unique posts (cost ${total_cost/1e6:.4f})")
    print(f"Balance: ${get_balance():.2f}")

    if save:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"posts": unique, "updated_at": datetime.now().astimezone().isoformat()}, f, indent=2)
        print(f"💾 Saved {len(unique)} posts to {STATE_FILE}")
    else:
        print(json.dumps(unique, indent=2)[:2000])

    return unique


if __name__ == "__main__":
    main()
