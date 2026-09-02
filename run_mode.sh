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
    # guest_outreach_engine.py requires a subcommand (CLI changed since run_mode.sh
    # was written — it used to run bare). Run a balanced daily outreach cycle:
    # discover new prospects, send a modest batch of pitches, then run follow-ups.
    echo "[$(date)] Guest mode — discover + send + followup"
    python scripts/guest_outreach_engine.py discover || true
    python scripts/guest_outreach_engine.py send --limit 5 || true
    python scripts/guest_outreach_engine.py followup || true
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
