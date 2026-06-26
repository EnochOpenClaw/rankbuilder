#!/bin/bash
# Maps RUN_MODE env var (or argument) to script execution
MODE="${1:-${RUN_MODE:-cron}}"
cd /app

echo "[$(date)] Starting mode: $MODE"

case "$MODE" in
  haro)
    python scripts/haro_monitor.py
    ;;
  connectively)
    python scripts/connectively_monitor.py
    ;;
  guest)
    python scripts/guest_outreach_engine.py
    ;;
  prospect)
    python scripts/prospect_checker.py
    ;;
  health)
    python -c "print('ok')"
    ;;
  cron)
    echo "Cron mode — individual jobs dispatched by cron daemon"
    ;;
  *)
    echo "Unknown mode: $MODE"
    exit 1
    ;;
esac

echo "[$(date)] Finished mode: $MODE"
