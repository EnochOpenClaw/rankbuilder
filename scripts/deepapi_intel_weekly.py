#!/usr/bin/env python3
"""
FortressBlinds Weekly Intel Run — combines SEO, competitor, and YouTube intel
into one scheduled report. Designed to run via cron.

Usage:
    python deepapi_intel_weekly.py          # Full weekly intel run
    python deepapi_intel_weekly.py --seo    # SEO only
    python deepapi_intel_weekly.py --comp   # Competitors only
    python deepapi_intel_weekly.py --yt     # YouTube only
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(BASE, "deepapi_seo.py")
COMP = os.path.join(BASE, "deepapi_competitors.py")
YT = os.path.join(BASE, "deepapi_youtube.py")


def run(cmd, label):
    print(f"\n{'='*50}\n{label}\n{'='*50}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-1500:])
    if r.returncode != 0:
        print(f"  ⚠️ {label} had errors: {r.stderr[-300:]}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seo", action="store_true")
    ap.add_argument("--comp", action="store_true")
    ap.add_argument("--yt", action="store_true")
    args = ap.parse_args()

    # Default: run all
    do_seo = args.seo or not (args.comp or args.yt)
    do_comp = args.comp or not (args.seo or args.yt)
    do_yt = args.yt or not (args.seo or args.comp)

    print(f"📊 FortressBlinds Weekly Intel Run — {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}")

    if do_seo:
        run([sys.executable, SCRIPTS, "scheduled-run"], "SEO Rank Tracking")
    if do_comp:
        run([sys.executable, COMP, "run"], "Competitor Intel")
    if do_yt:
        run([sys.executable, YT, "--save"], "YouTube Content Discovery")

    print("\n✅ Weekly intel run complete.")


if __name__ == "__main__":
    main()
