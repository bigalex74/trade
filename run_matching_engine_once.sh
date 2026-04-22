#!/bin/bash
set -u

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

exec /usr/bin/flock -n /tmp/matching_engine_once.lock \
  /home/user/trading_venv/bin/python /home/user/order_matching_engine.py
