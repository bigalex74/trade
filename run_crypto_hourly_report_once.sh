#!/bin/bash
set -u

LOCK_FILE="/tmp/crypto_hourly_report.lock"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/ai_crypto_hourly_report.py"

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Previous crypto hourly report is still running; skipping."
  exit 0
fi

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Generating crypto hourly report..."
exec "$PYTHON_BIN" "$SCRIPT"
