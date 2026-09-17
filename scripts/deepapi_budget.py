#!/usr/bin/env python3
"""
DeepAPI budget monitor — checks balance and alerts when below threshold.
Designed to run on a schedule (cron) and only alert when budget is low.
"""
import os
import sys

# Add rankbuilder lib to path
sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/rankbuilder/lib"))
from deepapi import get_balance

# Alert thresholds (USD) — alert at these levels
ALERT_THRESHOLD = float(os.environ.get("DEEPAPI_ALERT_USD", "3.0"))
CRITICAL_THRESHOLD = float(os.environ.get("DEEPAPI_CRITICAL_USD", "1.0"))
BALANCE_FILE = os.path.expanduser("~/.deepapi/.last_balance")

def main():
    balance = get_balance()
    if balance is None:
        print("DEEPAPI_BUDGET: Could not fetch balance (key missing or API down)")
        return 1

    # Balance may come back as str or float — normalize
    try:
        balance = float(balance)
    except (TypeError, ValueError):
        print(f"DEEPAPI_BUDGET: Unexpected balance value: {balance}")
        return 1

    print(f"DEEPAPI_BUDGET: ${balance:.2f} available")

    # Track if we've already alerted at this level (avoid spam)
    last_alerted_level = 0
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE) as f:
                last_alerted_level = int(f.read().strip())
        except Exception:
            pass

    # Determine alert level
    if balance <= CRITICAL_THRESHOLD and last_alerted_level < 2:
        print(f"DEEPAPI_CRITICAL: Balance ${balance:.2f} is critically low (below ${CRITICAL_THRESHOLD}). Top up at https://deepapi.co/credits")
        with open(BALANCE_FILE, "w") as f:
            f.write("2")
    elif balance <= ALERT_THRESHOLD and last_alerted_level < 1:
        print(f"DEEPAPI_ALERT: Balance ${balance:.2f} is running low (below ${ALERT_THRESHOLD}). Consider topping up at https://deepapi.co/credits")
        with open(BALANCE_FILE, "w") as f:
            f.write("1")

    return 0

if __name__ == "__main__":
    sys.exit(main())
