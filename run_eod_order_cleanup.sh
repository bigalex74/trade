#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${HOME:-/home/user}"
PYTHON_BIN="${PYTHON_BIN:-${USER_HOME}/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/eod_order_cleanup.py"
LOG_DIR="${USER_HOME}/logs"

mkdir -p "$LOG_DIR"

timestamp() {
  date -Is
}

echo "[$(timestamp)] EOD Order Cleanup: start"

if "$PYTHON_BIN" "$SCRIPT"; then
  echo "[$(timestamp)] EOD Order Cleanup: success"
else
  status=$?
  echo "[$(timestamp)] EOD Order Cleanup: failed with exit code $status" >&2
  exit "$status"
fi
