#!/usr/bin/env python3
"""
LinkedIn API posting via OAuth2.
Handles token refresh, API calls, and error recovery.
"""

import json, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from credentials import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_ACCESS_TOKEN

# ============================================================================
# CONFIG
# ============================================================================

TOKEN_FILE = Path(__file__).parent.parent / ".linkedin_token.json"
API_BASE = "https://api.linkedin.com/rest"
UGC_BASE = "https://api.linkedin.com/v2"

# ============================================================================
# TOKEN MANAGEMENT
# ============================================================================

def load_token() -> dict:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {"access_token": LINKEDIN_ACCESS_TOKEN, "expires_at": None}

def save_token(token_data: dict):
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))

def refresh_access_token() -> dict:
    """Exchange client credentials for a new access token."""
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://www.linkedin.com/oauth/v2/accessToken",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-d", f"grant_type=client_credentials&client_id={LINKEDIN_CLIENT_ID}&client_secret={LINKEDIN_CLIENT_SECRET}"
    ], capture_output=True, text=True)
    
    try:
        data = json.loads(result.stdout)
        if "access_token" in data:
            token_data = {
                "access_token": data["access_token"],
                "expires_at": (datetime.now() + timedelta(seconds=data.get("expires_in", 5184000))).isoformat()
            }
            save_token(token_data)
            return token_data
        else:
            return {"error": data.get("error_description", "Unknown error")}
    except:
        return {"error": "Failed to parse token response"}

def get_valid_token() -> str:
    """Get a valid access token, refreshing if needed."""
    token_data = load_token()
    
    # Check if expired
    if token_data.get("expires_at"):
        expires = datetime.fromisoformat(token_data["expires_at"])
        if datetime.now() >= expires - timedelta(hours=1):
            refreshed = refresh_access_token()
            if "error" not in refreshed:
                return refreshed["access_token"]
    
    return token_data.get("access_token", LINKEDIN_ACCESS_TOKEN)

# ============================================================================
# LINKEDIN API CALLS
# ============================================================================

def api_get(endpoint: str) -> dict:
    """Make an authenticated GET request to LinkedIn API."""
    token = get_valid_token()
    result = subprocess.run([
        "curl", "-s", "-X", "GET",
        f"{API_BASE}{endpoint}",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/json",
        "-H", "X-Restli-Protocol-Version: 2.0.0"
    ], capture_output=True, text=True)
    
    try:
        return json.loads(result.stdout)
    except:
        return {"error": "parse_error", "raw": result.stdout[:200]}

def api_post(endpoint: str, payload: dict) -> dict:
    """Make an authenticated POST request to LinkedIn API."""
    token = get_valid_token()
    data = json.dumps(payload)
    
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"{API_BASE}{endpoint}",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-H", "X-Restli-Protocol-Version: 2.0.0",
        "-d", data
    ], capture_output=True, text=True)
    
    try:
        return json.loads(result.stdout)
    except:
        return {"error": "parse_error", "raw": result.stdout[:200]}

# ============================================================================
# PROFILE (who am I?)
# ============================================================================

def get_my_profile() -> dict:
    """Get current user's LinkedIn profile."""
    return api_get("/me")

def get_profile_photo() -> dict:
    """Get profile photo URLs."""
    return api_get("/me/profilePhoto")

# ============================================================================
# POSTING
# ============================================================================

def post_article(title: str, body: str, article_url: str = None) -> dict:
    """
    Post an article to LinkedIn personal profile.
    
    LinkedIn articles are created via the ugcPosts API:
    POST https://api.linkedin.com/v2/ugcPosts
    
    The author must be: urn:li:person:{personId}
    We get the person ID from /v2/me
    """
    token = get_valid_token()
    
    # First get my person URN
    profile = api_get("/me")
    person_id = profile.get("id")
    if not person_id:
        return {"error": "Could not get LinkedIn ID", "profile": profile}
    
    author = f"urn:li:person:{person_id}"
    
    # Build the article payload
    article_content = {
        "article": {
            "title": title,
            "description": body[:300],  # LinkedIn truncates description
        }
    }
    if article_url:
        article_content["article"]["sourceUrl"] = article_url
    
    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": body[:1300]},  # LinkedIn limit for article body
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "originalUrl": article_url or ""
                }] if article_url else []
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    
    return api_post("/ugcPosts", payload)

def post_text_update(text: str) -> dict:
    """Post a simple text update (short post)."""
    token = get_valid_token()
    
    profile = api_get("/me")
    person_id = profile.get("id")
    if not person_id:
        return {"error": "Could not get LinkedIn ID", "profile": profile}
    
    author = f"urn:li:person:{person_id}"
    
    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    
    return api_post("/ugcPosts", payload)

# ============================================================================
# MAIN — Test / Status
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LinkedIn API posting")
    parser.add_argument("--whoami", action="store_true", help="Show my LinkedIn profile")
    parser.add_argument("--test", action="store_true", help="Test token validity")
    parser.add_argument("--post", type=str, help="Post a text update")
    parser.add_argument("--title", type=str, help="Article title")
    parser.add_argument("--body", type=str, help="Article body")
    parser.add_argument("--url", type=str, help="Article URL")
    
    args = parser.parse_args()
    
    if args.whoami:
        print("Fetching LinkedIn profile...")
        profile = get_my_profile()
        if "id" in profile:
            print(f"✅ Logged in as: {profile.get('id')}")
            print(f"   Name: {profile.get('localizedFirstName','')} {profile.get('localizedLastName','')}")
        else:
            print(f"❌ Profile error: {profile}")
    
    elif args.test:
        token = get_valid_token()
        profile = api_get("/me")
        if "id" in profile:
            print(f"✅ Token valid. LinkedIn ID: {profile.get('id')}")
        else:
            error = profile.get("error", {})
            if isinstance(error, dict):
                code = error.get("code", "")
                msg = error.get("message", "")
                print(f"❌ Token invalid/error: {code} — {msg}")
                if code == "INVALID_ACCESS_TOKEN":
                    print("\n💡 The app may need compliance review. Use Playwright for immediate posting.")
            else:
                print(f"❌ {profile}")
    
    elif args.post:
        print(f"Posting: {args.post[:50]}...")
        result = post_text_update(args.post)
        if "id" in result:
            print(f"✅ Posted! ID: {result['id']}")
        else:
            print(f"❌ Error: {result}")
    
    elif args.title:
        result = post_article(args.title, args.body or "", args.url)
        if "id" in result:
            print(f"✅ Article posted! ID: {result['id']}")
        else:
            print(f"❌ Error: {result}")
    
    else:
        print("LinkedIn API posting tool")
        print("  --whoami           Show your LinkedIn profile")
        print("  --test             Test if token is valid")
        print("  --post 'text'      Post a text update")
        print("  --title 't' --body 'b' --url 'u'   Post an article")