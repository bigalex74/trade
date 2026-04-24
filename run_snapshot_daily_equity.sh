#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${HOME:-/home/user}"
PYTHON_BIN="${PYTHON_BIN:-${USER_HOME}/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/snapshot_daily_equity.py"
LOG_DIR="${USER_HOME}/logs"

mkdir -p "$LOG_DIR"

timestamp() {
  date -Is
}

echo "[$(timestamp)] Daily Equity Snapshot: start"

if "$PYTHON_BIN" "$SCRIPT"; then
  echo "[$(timestamp)] Daily Equity Snapshot: success"
else
  status=$?
  echo "[$(timestamp)] Daily Equity Snapshot: failed with exit code $status" >&2
  exit "$status"
fi
