#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="/tmp/market_research_refresh_daily.lock"
PYTHON_BIN="/home/user/trading_venv/bin/python3"
PIPELINE_SCRIPT="/home/user/market_research_market_pipeline.py"

mkdir -p /home/user/logs

timestamp() {
  date -Is
}

echo "[$(timestamp)] market_research refresh daily: start"

if flock -E 99 -n "$LOCK_FILE" "$PYTHON_BIN" "$PIPELINE_SCRIPT" refresh-context --mode daily; then
  echo "[$(timestamp)] market_research refresh daily: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] market_research refresh daily: skipped, previous run still active"
    exit 0
  fi
  echo "[$(timestamp)] market_research refresh daily: failed with exit code $status" >&2
  exit "$status"
fi
