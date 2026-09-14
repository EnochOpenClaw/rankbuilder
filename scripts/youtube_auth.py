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
PORT = int(os.environ.get("YT_AUTH_PORT", "18789"))
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


def exchange_code(client, code, redirect_uri):
    r = httpx.post(TOKEN_URL, data={
        "code": code,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=30)
    if r.status_code != 200:
        print(f"❌ Token exchange failed: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    return r.json()


def main():
    client = load_client()
    redirect_uri = f"http://127.0.0.1:{PORT}/"

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
                body = b"<html><body><h3>✓ Authorized. You can close this window.</h3></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = b"<html><body><h3>No code received — close and retry.</h3></body></html>"
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

    tokens = exchange_code(client, state["code"], redirect_uri)
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
