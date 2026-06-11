#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
timeout 90 python3 "$SCRIPT_DIR/prospect_discovery.py" --batch --limit 10 --quiet 2>&1
