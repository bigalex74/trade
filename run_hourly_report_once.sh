#!/bin/bash
set -u

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

exec /usr/bin/flock -n /tmp/hourly_report_once.lock \
  /home/user/trading_venv/bin/python /home/user/ai_hourly_report.py
