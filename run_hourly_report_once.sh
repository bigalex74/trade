#!/bin/bash
set -u

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

exec /usr/bin/flock -n /tmp/hourly_report_once.lock \
  "$PYTHON_BIN" "${PROJECT_DIR}/ai_hourly_report.py"
