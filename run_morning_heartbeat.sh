#!/usr/bin/env bash
set -euo pipefail

USER_HOME="${HOME:-/home/user}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${USER_HOME}/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/morning_heartbeat.py"

if [ -f "${USER_HOME}/.env.trading" ]; then
  set -a
  source "${USER_HOME}/.env.trading"
  set +a
fi

timestamp() {
  date -Is
}

echo "[$(timestamp)] Morning Heartbeat: start"
if "$PYTHON_BIN" "$SCRIPT"; then
  echo "[$(timestamp)] Morning Heartbeat: SUCCESS"
else
  status=$?
  echo "[$(timestamp)] Morning Heartbeat: FAILED with exit code $status" >&2
  exit "$status"
fi
