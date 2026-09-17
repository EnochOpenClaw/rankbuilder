#!/usr/bin/env python3
"""
DeepAPI client — reusable module for RankBuilder.
Wraps DeepAPI endpoints (search, SEO, scrape, research) with cost caps,
idempotency, polling, and balance tracking.

Config: reads DEEPAPI_API_KEY from env or ~/.deepapi/env.
"""
import json
import os
import time
import uuid
import urllib.request
import urllib.error

BASE = "https://deepapi.co"


def _load_key():
    """Load DEEPAPI_API_KEY from env or ~/.deepapi/env."""
    key = os.environ.get("DEEPAPI_API_KEY", "")
    if not key:
        env_file = os.path.expanduser("~/.deepapi/env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith("export DEEPAPI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return key


def get_balance():
    """Return available balance in USD (float), or None."""
    key = _load_key()
    if not key:
        return None
    req = urllib.request.Request(f"{BASE}/v1/balance", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        out = d.get("output") or {}
        val = out.get("availableUsd")
        if val is None:
            val = out.get("availableMicrousd", 0) / 1e6
        return float(val)
    except Exception:
        return None


def call(path, body, label="", follow_poll=True, max_polls=10):
    """
    POST to a DeepAPI endpoint. Returns the parsed response dict.
    - Adds Authorization + Idempotency-Key + Content-Type headers.
    - If follow_poll and the response has a GET polling next, follows it.
    """
    key = _load_key()
    if not key:
        raise RuntimeError("DEEPAPI_API_KEY not set. Run the DeepAPI installer or set it in ~/.deepapi/env")

    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"rb-{uuid.uuid4().hex[:16]}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        d = json.loads(e.read().decode())

    # Follow GET polling next if present
    if follow_poll:
        for _ in range(max_polls):
            nxt = d.get("next")
            if nxt and nxt.get("method") == "GET" and nxt.get("path", "").startswith("/v1/requests/"):
                time.sleep(nxt.get("afterSecs") or 3)
                req2 = urllib.request.Request(f"{BASE}{nxt['path']}", headers={"Authorization": f"Bearer {key}"})
                try:
                    with urllib.request.urlopen(req2, timeout=60) as r2:
                        d = json.loads(r2.read().decode())
                except Exception:
                    break
            else:
                break
    return d


# ── Convenience wrappers ────────────────────────────────────────────────────

def web_search(query, max_results=10, max_cost_usd="0.10"):
    """Open-web search. Returns output dict. Uses maxResults field."""
    return call("/v1/search/web", {"query": query, "maxResults": max_results, "maxCostUsd": max_cost_usd})


def seo_keywords(keywords, max_cost_usd="0.125"):
    """Batch SEO keyword research (up to 100 keywords)."""
    if isinstance(keywords, str):
        keywords = [keywords]
    return call("/v1/seo/keyword", {"keywords": keywords, "maxCostUsd": max_cost_usd})


def seo_rank(domain, keyword, max_cost_usd="0.10"):
    """Check domain rank for a keyword."""
    return call("/v1/seo/rank", {"domain": domain, "keyword": keyword, "maxCostUsd": max_cost_usd})


def reddit_search(query, max_items=10, max_cost_usd="0.15"):
    """Reddit search (RankBuilder Reddit module)."""
    return call("/v1/scrape/reddit/search", {"query": query, "maxItems": max_items, "maxCostUsd": max_cost_usd})


def youtube_search(query, max_items=10, max_cost_usd="0.10"):
    """YouTube search."""
    return call("/v1/scrape/youtube/search", {"query": query, "maxItems": max_items, "maxCostUsd": max_cost_usd})


def scrape_website(urls, max_chars=5000, max_pages=5, max_cost_usd="0.15"):
    """Scrape one or more website pages."""
    if isinstance(urls, str):
        urls = [urls]
    return call("/v1/scrape/website", {"urls": urls, "contentFormat": "markdown", "maxChars": max_chars, "maxPages": max_pages, "maxCostUsd": max_cost_usd})


def generate_image(prompt, max_cost_usd="0.30"):
    """Generate an image. Returns base64 JPEG in output['images'][0]."""
    return call("/v1/generate/image", {"prompt": prompt, "maxCostUsd": max_cost_usd})
