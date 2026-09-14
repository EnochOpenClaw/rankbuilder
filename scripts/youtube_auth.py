#!/usr/bin/env python3
"""
youtube_auth.py — OAuth for the Fortress Blinds YouTube channel (one-time).

Setup:
  1. Download the OAuth client file from Google Cloud Console
     (APIs & Services → Credentials → OAuth 2.0 Client IDs →
      Desktop app → Download JSON) and save it as client_secret.json
     in this directory.
  2. Run:  python3 youtube_auth.py
     It prints the Google consent URL, waits for the loopback callback,
     exchanges the code, and writes youtube_token.json (used by
     youtube_upload.py, which auto-refreshes afterwards).
  3. Approve the consent screen with the Google account that owns the
     Fortress Blinds YouTube channel.

Port: defaults to 18789 to match the loopback redirect URI the original
client used; override with YT_AUTH_PORT if your client registered a
different one (redirect_uri must match EXACTLY).
"""
import json
import os
import sys
import argparse
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Timer

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

BASE = os.path.dirname(os.path.abspath(__file__))
CLIENT_FILE = os.path.join(BASE, "client_secret.json")
TOKEN_FILE = os.path.join(BASE, "youtube_token.json")
PORT = int(os.environ.get("YT_AUTH_PORT", "8080"))  # matches RankBuilder YouTube client's registered redirect
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
         "https://www.googleapis.com/auth/youtube.readonly")


def load_client():
    if not os.path.exists(CLIENT_FILE):
        print(f"❌ client_secret.json not found — expected at: {CLIENT_FILE}")
        print("   Download it from Google Cloud Console → Credentials →")
        print("   OAuth 2.0 Client IDs → your Desktop client → Download JSON.")
        sys.exit(1)
    with open(CLIENT_FILE) as f:
        data = json.load(f)
    key = "installed" if "installed" in data else ("web" if "web" in data else None)
    if key is None:
        print("❌ client_secret.json has no 'installed'/'web' section:", list(data.keys()))
        sys.exit(1)
    return data[key]


def get_secret(client):
    """Full client secret: env override (protected store) or client_secret.json."""
    env_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    return env_secret or client.get("client_secret")


def exchange_code(client, secret, code, redirect_uri):
    if not secret:
        print("❌ No client secret available. Google masks it now — create a new one")
        print("   in Cloud Console (Credentials → RankBuilder YouTube → ");
        print("   Create new client secret / add new one), then retry with it set.")
        sys.exit(1)
    r = httpx.post(TOKEN_URL, data={
        "code": code,
        "client_id": client["client_id"],
        "client_secret": secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=30)
    if r.status_code != 200:
        print(f"❌ Token exchange failed: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    return r.json()


def main():
    ap = argparse.ArgumentParser(description="YouTube OAuth — Fortress Blinds channel (one-time setup)")
    ap.add_argument("--code", help="Authorization code from the consent URL callback — use this when the browser cannot reach localhost (paste the full code value)")
    args = ap.parse_args()

    client = load_client()
    redirect_uri = f"http://localhost:{PORT}"  # exact match with console registration

    # ── Manual path: code passed in (browser can't hit localhost) ──
    if args.code:
        code = args.code.strip()
        print(f"Exchanging code ({len(code)} chars) with stored client...")
        tokens = exchange_code(client, get_secret(client), code, redirect_uri)
        if "refresh_token" not in tokens:
            print("❌ No refresh_token returned. Check the client's consent screen status.")
            sys.exit(1)
        payload = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": tokens.get("token_type", "Bearer"),
            "expires_in": tokens.get("expires_in", 3600),
        }
        with open(TOKEN_FILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\n✅ youtube_token.json written to {TOKEN_FILE}")
        print("   Checking the token against YouTube...")
        try:
            r = httpx.get(
                "https://www.googleapis.com/youtube/v3/channels?mine=true&part=id",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=15,
            )
            if r.status_code == 200:
                ch = r.json().get("items", [{}])[0].get("id", "?")
                print(f"✅ Token valid — authenticated channel id: {ch}")
            else:
                print(f"⚠️  Token check returned {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"⚠️  Token check failed: {e}")
        return

    # ── Interactive path: start local callback server, print consent URL ──

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    state = {"code": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path)
            args = urllib.parse.parse_qs(q.query)
            if "code" in args:
                state["code"] = args["code"][0]
                body = b"<html><body><h3>Authorized. You can close this window.</h3></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = b"<html><body><h3>No code received - close and retry.</h3></body></html>"
                self.send_response(400)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            Timer(0.5, lambda: (server.shutdown(), server.server_close())).start()

        def log_message(self, *a):  # quiet
            pass

    print("=" * 62)
    print("YouTube OAuth — Fortress Blinds channel (one-time setup)")
    print("=" * 62)
    print("Open this URL and approve with the Google account that owns")
    print("the Fortress Blinds YouTube channel:\n")
    print(url)
    print()
    try:
        webbrowser.open(url)
    except Exception:
        pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    server.handle_request()  # blocks until callback received

    if not state["code"]:
        print("❌ No authorization code received.")
        sys.exit(1)

    tokens = exchange_code(client, get_secret(client), state["code"], redirect_uri)
    if "refresh_token" not in tokens:
        print("❌ No refresh_token returned. Re-run with prompt=consent (already set) "
              "or check the client's consent screen status.")
        sys.exit(1)

    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in", 3600),
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n✅ youtube_token.json written to {TOKEN_FILE}")
    print("   You can now run youtube_upload.py.")


if __name__ == "__main__":
    main()
