#!/bin/bash
# HARO Monitor cron runner
# Runs every 30 minutes, logs to rankbuilder/logs/cron.log

SCRIPT_DIR="/home/enoch/.openclaw/workspace/rankbuilder/scripts"
LOG_DIR="/home/enoch/.openclaw/workspace/rankbuilder/logs"
MAX_LOG_LINES=100

mkdir -p "$LOG_DIR"

# Run the monitor
cd /home/enoch/.openclaw/workspace
python3 "$SCRIPT_DIR/haro_monitor.py" >> "$LOG_DIR/cron.log" 2>&1

# Keep log files from growing too large
if [ -f "$LOG_DIR/cron.log" ]; then
    tail -n $MAX_LOG_LINES "$LOG_DIR/cron.log" > "$LOG_DIR/cron.log.tmp"
    mv "$LOG_DIR/cron.log.tmp" "$LOG_DIR/cron.log"
fi