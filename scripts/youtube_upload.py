#!/usr/bin/env python3
"""
YouTube video uploader — Fortress Blinds channel.
Uploads a video to the authorized YouTube channel via the Data API v3
resumable upload endpoint. Auto-refreshes the OAuth token when needed.

Usage:
    python3 youtube_upload.py <video.mp4> [--title "TITLE"] [--description "DESC"]
                             [--tags "a,b,c"] [--privacy public|unlisted|private]
                             [--category 22]

Requires youtube_token.json (from youtube_auth_server.py) + client_secret.json.
"""
import argparse
import json
import os
import sys
import time

import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE, "youtube_token.json")
CLIENT_FILE = os.path.join(BASE, "client_secret.json")
DEFAULT_CATEGORY = 26


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)


def load_secrets():
    with open(CLIENT_FILE) as f:
        return json.load(f)["installed"]


def refresh_access_token(tokens, secrets):
    payload = {
        "client_id": secrets["client_id"],
        "client_secret": secrets["client_secret"],
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    }
    r = httpx.post(secrets["token_uri"], data=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {r.status_code} {r.text[:300]}")
    new_tokens = r.json()
    tokens.update(new_tokens)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    return tokens["access_token"]


def get_valid_access_token():
    tokens = load_tokens()
    secrets = load_secrets()
    r = httpx.get(
        "https://www.googleapis.com/youtube/v3/channels?mine=true&part=id",
        headers={"Authorization": "Bearer " + tokens.get("access_token")},
        timeout=15,
    )
    if r.status_code == 200:
        return tokens["access_token"]
    return refresh_access_token(tokens, secrets)


def upload_video(access_token, video_path, title, description, tags, privacy, category):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    size = os.path.getsize(video_path)

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
            "categoryId": str(category),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(size),
        "X-Upload-Content-Type": "video/*",
    }

    init = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers=headers,
        json=metadata,
        timeout=30,
    )
    if init.status_code != 200:
        raise RuntimeError(f"Upload init failed: {init.status_code} {init.text[:400]}")
    upload_url = init.headers.get("Location")
    if not upload_url:
        raise RuntimeError("No upload URL returned")

    print(f"  Uploading {size / 1_000_000.0:.1f} MB...")
    with open(video_path, "rb") as f:
        data = f.read()
    headers2 = {"Content-Type": "video/*", "Content-Length": str(size)}
    upload = httpx.put(upload_url, headers=headers2, content=data, timeout=300)
    if upload.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed: {upload.status_code} {upload.text[:400]}")
    result = upload.json()
    return result


def main():
    ap = argparse.ArgumentParser(description="Upload video to Fortress Blinds YouTube")
    ap.add_argument("video", help="Path to the video file (.mp4)")
    ap.add_argument("--title", required=True, help="Video title (max 100 chars)")
    ap.add_argument("--description", default="", help="Video description")
    ap.add_argument("--tags", default="", help="Comma-separated tags")
    ap.add_argument("--privacy", default="unlisted", choices=("public", "unlisted", "private"),
                    help="Privacy status (default: unlisted)")
    ap.add_argument("--category", type=int, default=DEFAULT_CATEGORY, help="YouTube category ID")
    args = ap.parse_args()

    if len(args.title) > 100:
        print(f"⚠️  Title too long ({len(args.title)} chars). YouTube allows 100. Truncating.")
        args.title = args.title[:100]

    print(f"🎬 Uploading: {os.path.basename(args.video)}")
    print(f"   Title: {args.title}")
    print(f"   Privacy: {args.privacy}")

    token = get_valid_access_token()
    print("✅ Authenticated with YouTube")

    result = upload_video(token, args.video, args.title, args.description, args.tags, args.privacy, args.category)
    vid = result.get("id", "?")
    status = result.get("status", {}).get("uploadStatus", "?")

    print("\n✅ Upload complete!")
    print(f"   Video ID: {vid}")
    print(f"   Upload status: {status}")
    print(f"   URL: https://www.youtube.com/watch?v={vid}")
    print("   (may take a few minutes to process)")


if __name__ == "__main__":
    main()
