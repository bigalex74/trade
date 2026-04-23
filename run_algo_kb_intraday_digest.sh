#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOCK_FILE="${ALGO_KB_INTRADAY_DIGEST_LOCK_FILE:-/tmp/algo_kb_intraday_digest.lock}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/algo_kb_intraday_digest.py"

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

mkdir -p /home/user/logs

timestamp() {
  date -Is
}

echo "[$(timestamp)] algo kb intraday digest: start"

if flock -E 99 -n "$LOCK_FILE" "$PYTHON_BIN" "$SCRIPT" "$@"; then
  echo "[$(timestamp)] algo kb intraday digest: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] algo kb intraday digest: skipped, previous run still active"
    exit 0
  fi
  echo "[$(timestamp)] algo kb intraday digest: failed with exit code $status" >&2
  exit "$status"
fi
