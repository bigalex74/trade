#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOCK_FILE="/tmp/algo_kb_market_summary.lock"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/algo_kb_market_summary.py"

mkdir -p /home/user/logs

timestamp() {
  date -Is
}

echo "[$(timestamp)] algo kb market summary: start"

if flock -E 99 -n "$LOCK_FILE" "$PYTHON_BIN" "$SCRIPT"; then
  echo "[$(timestamp)] algo kb market summary: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] algo kb market summary: skipped, previous run still active"
    exit 0
  fi
  echo "[$(timestamp)] algo kb market summary: failed with exit code $status" >&2
  exit "$status"
fi
