#!/usr/bin/env python3
"""
buffer_poster_fortressblinds.py — Post FortressBlinds content to LinkedIn via Buffer MCP.
Connects to: https://mcp.buffer.com/mcp (FortressBlinds Buffer account)
Token: WbiQPf…aWZ1
"""
import subprocess, json, sys, os
from datetime import datetime, timedelta
import pytz

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY = os.path.join(SCRIPT_DIR, "buffer_mcp_proxy_fortressblinds.py")

BUFFER_KEY = "WbiQPfVdXXeFnH12Pr49yIv6-_HENwoXTfJkIvjaWZ1"
BUFFER_URL = "https://mcp.buffer.com/mcp"

def call_mcp(tool_name, args=None):
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args or {}}
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {BUFFER_KEY}",
    }
    import urllib.request, urllib.error
    req = urllib.request.Request(BUFFER_URL, data=payload.encode("utf-8"),
                                  headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            for line in body.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(body)
        except:
            return {"error": {"code": e.code, "message": body[:300]}}
    except Exception as e:
        return {"error": {"code": -32603, "message": str(e)}}

def is_error(r):
    if isinstance(r, str): return True, r
    if not isinstance(r, dict): return False, None
    err = r.get("error")
    if err: return True, str(err) if isinstance(err, str) else err.get("message", str(err))
    return False, None

def get_org():
    r = call_mcp("get_account", {})
    ok, err = is_error(r)
    if ok: return None, err
    text = r.get("result", {}).get("content", [{}])[0].get("text", "{}")
    data = json.loads(text)
    return data["organizations"][0]["id"], None

def get_linkedin_channel(org_id):
    r = call_mcp("list_channels", {"organizationId": org_id})
    ok, err = is_error(r)
    if ok: return None, err
    text = r.get("result", {}).get("content", [{}])[0].get("text", "{}")
    data = json.loads(text)
    channels = data if isinstance(data, list) else data.get("channels", [])
    for ch in channels:
        if ch.get("service", "").lower() == "linkedin":
            return ch["id"], None
    return None, f"No LinkedIn channel found. Channels: {[c.get('service') for c in channels]}"

def create_post(channel_id, text, due_at=None):
    args = {
        "channelId": channel_id,
        "schedulingType": "automatic",
        "text": text,
    }
    if due_at:
        args["dueAt"] = due_at.isoformat()
    r = call_mcp("create_post", args)
    ok, err = is_error(r)
    if ok: return False, err
    post_id = r.get("result", {}).get("content", [{}])[0].get("text", "")
    if post_id:
        try:
            data = json.loads(post_id)
            return True, data.get("id", post_id)
        except:
            return True, post_id
    return False, str(r)

def next_post_time(day_offset=0, hour=9):
    """Next SAST 9am post time, optionally N days from now."""
    sa = pytz.timezone("Africa/Johannesburg")
    now = datetime.now(sa)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
    if target <= now:
        target += timedelta(days=1)
    return target

def next_weekday_post(weekday_target, hour=9):
    """Next occurrence of a weekday (0=Mon..6=Sun) at SAST hour."""
    sa = pytz.timezone("Africa/Johannesburg")
    now = datetime.now(sa)
    days_ahead = (weekday_target - now.weekday()) % 7
    if days_ahead == 0 and now.replace(hour=hour, minute=0, second=0, microsecond=0) <= now:
        days_ahead = 7  # already past today, go to next week
    elif days_ahead == 0:
        days_ahead = 0  # today is the day and we haven't passed the time yet
    target = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return target

def load_posts():
    """Load FortressBlinds posts from the draft file."""
    draft_file = os.path.join(SCRIPT_DIR, "..", "social-posts", "draft_fortressblinds_week1.md")
    if not os.path.exists(draft_file):
        return []
    with open(draft_file) as f:
        content = f.read()
    posts = []
    current_post = None
    for line in content.split("\n"):
        if line.startswith("## POST"):
            if current_post:
                posts.append(current_post)
            current_post = {"text": ""}
        elif current_post is not None and line.startswith(">"):
            current_post["text"] += line[1:].strip() + "\n"
    if current_post:
        posts.append(current_post)
    for p in posts:
        p["text"] = p["text"].strip()
    return posts

if __name__ == "__main__":
    print("=== FortressBlinds Buffer Poster ===")
    org_id, err = get_org()
    if err:
        print(f"❌ Org error: {err}")
        sys.exit(1)
    print(f"✅ Org: {org_id}")

    ch_id, err = get_linkedin_channel(org_id)
    if err:
        print(f"❌ Channel error: {err}")
        sys.exit(1)
    print(f"✅ LinkedIn channel: {ch_id}")

    posts = load_posts()
    print(f"Loaded {len(posts)} posts")

    # Schedule Mon(0) Wed(2) Fri(4) Sat(5) — weekday numbers
    weekdays = [0, 2, 4, 5]
    for i, post in enumerate(posts):
        due = next_weekday_post(weekdays[i])
        ok, result = create_post(ch_id, post["text"], due_at=due)
        if ok:
            print(f"✅ Post {i+1} scheduled for {due.strftime('%a %Y-%m-%d %H:%M %Z')}")
        else:
            print(f"❌ Post {i+1} failed: {result}")
