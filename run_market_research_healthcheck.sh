#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="/tmp/market_research_healthcheck.lock"
PYTHON_BIN="/home/user/trading_venv/bin/python3"
MAINTENANCE_SCRIPT="/home/user/market_research_maintenance.py"

mkdir -p /home/user/logs

timestamp() {
  date -Is
}

echo "[$(timestamp)] market_research healthcheck: start"

if flock -E 99 -n "$LOCK_FILE" "$PYTHON_BIN" "$MAINTENANCE_SCRIPT" health-check; then
  echo "[$(timestamp)] market_research healthcheck: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] market_research healthcheck: skipped, previous run still active"
    exit 0
  fi
  echo "[$(timestamp)] market_research healthcheck: failed with exit code $status" >&2
  exit "$status"
fi
