#!/usr/bin/env python3
"""
Lightweight prospect count checker + optional auto-discovery trigger.
Runs every 3 days. If new_prospects < threshold, fires a discovery agent.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Container path vs local path
CONTAINER_PATH = Path("/app")
LOCAL_PATH    = Path.home() / ".openclaw" / "workspace" / "rankbuilder"
WORKSPACE      = Path("/app") if Path("/app").exists() else LOCAL_PATH

PROSPECT_DB = WORKSPACE / "prospects" / "prospect_db.json"
THRESHOLD   = 12
DRY_RUN     = "--dry-run" in sys.argv

def count_new():
    if not PROSPECT_DB.exists():
        return 0
    with open(PROSPECT_DB) as f:
        db = json.load(f)
    return sum(1 for p in db["prospects"].values() if p.get("status") == "new")

def trigger_discovery():
    print(f"[{datetime.now().isoformat()}] 🔍 Prospect count low — triggering discovery")
    result = subprocess.run(
        ["python3", "scripts/web_search_discovery.py", "add-sa"],
        cwd=WORKSPACE,
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0

def main():
    count = count_new()
    print(f"[{datetime.now().isoformat()}] 📊 Prospect check: {count} new prospects (threshold={THRESHOLD})")

    if DRY_RUN:
        print("[dry-run] Skipping actual send")
        return

    if count < THRESHOLD:
        print(f"⚠️  {count} < {THRESHOLD} — running discovery...")
        trigger_discovery()
        count2 = count_new()
        print(f"✅ Discovery done. New count: {count2}")
    else:
        print(f"✅ {count} prospects — no discovery needed")

if __name__ == "__main__":
    main()
