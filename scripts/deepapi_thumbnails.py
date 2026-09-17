#!/usr/bin/env python3
"""
FortressBlinds YouTube Thumbnail Generator — powered by DeepAPI.
Generates custom YouTube thumbnails (1280x720) using DeepAPI image generation
for the FortressBlinds video content.

Usage:
    python deepapi_thumbnails.py generate "<prompt>" -o <output.png>
    python deepapi_thumbnails.py generate-all   # Generate for all target videos
"""
import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import generate_image, get_balance

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "thumbnails")

# Thumbnail prompts for FortressBlinds videos (1280x720 style)
THUMBNAIL_PROMPTS = [
    {
        "name": "rollerscreen_demo",
        "prompt": ("Modern aluminium security rollerscreen on a South African home window, "
                   "half-open showing the mesh, dramatic blue-sky backdrop, bold and clean "
                   "marketing thumbnail style, high contrast, 16:9 widescreen"),
    },
    {
        "name": "security_screen_showroom",
        "prompt": ("Close-up of a strong metal security screen door on a modern home, "
                   "professional product shot, dark elegant background with subtle gold accent, "
                   "premium marketing thumbnail, 16:9 widescreen"),
    },
    {
        "name": "shutters_coastal",
        "prompt": ("Luxury coastal home with white aluminium shutters, ocean view, bright daylight, "
                   "aspirational lifestyle marketing thumbnail, 16:9 widescreen"),
    },
]


def save_image_from_result(result, out_path):
    """Extract base64 image from DeepAPI response and save it."""
    out = result.get("output") or {}
    images = out.get("images") or []
    if not images:
        print(f"  ⚠️ No image in response. status={result.get('status')} error={result.get('error')}")
        return False
    b64 = images[0]
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    data = base64.b64decode(b64)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"  💾 Saved: {out_path} ({len(data)//1024} KB)")
    return True


def cmd_generate(prompt, output):
    print(f"🎨 Generating thumbnail | Balance: ${get_balance():.2f}")
    print(f"   Prompt: {prompt[:70]}...")
    result = generate_image(prompt, max_cost_usd="0.35")
    print(f"   Status: {result.get('status')} | Cost: {result.get('debitMicrousd')} micro-USD")
    if result.get("status") == "succeeded":
        return save_image_from_result(result, output)
    else:
        print(f"   Error: {result.get('error')}")
        return False


def cmd_generate_all():
    print(f"🎨 Generating {len(THUMBNAIL_PROMPTS)} thumbnails | Balance: ${get_balance():.2f}")
    for item in THUMBNAIL_PROMPTS:
        out = os.path.join(OUT_DIR, f"thumb_{item['name']}.jpg")
        print(f"\n--- {item['name']} ---")
        result = generate_image(item["prompt"], max_cost_usd="0.35")
        print(f"   Status: {result.get('status')} | Cost: {result.get('debitMicrousd')} micro-USD")
        if result.get("status") == "succeeded":
            save_image_from_result(result, out)
    print(f"\n✅ Done. Balance: ${get_balance():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate YouTube thumbnails via DeepAPI")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("generate")
    g.add_argument("prompt")
    g.add_argument("-o", "--output", required=True)
    sub.add_parser("generate-all")
    args = ap.parse_args()

    if args.cmd == "generate":
        cmd_generate(args.prompt, args.output)
    elif args.cmd == "generate-all":
        cmd_generate_all()
    else:
        ap.print_help()
