#!/bin/bash
set -euo pipefail

cd /home/user

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

export AI_JOB_MAX_WORKERS="${AI_JOB_MAX_WORKERS:-2}"
export AI_JOB_START_BATCH="${AI_JOB_START_BATCH:-1}"
export AI_JOB_DISPATCH_TICKS="${AI_JOB_DISPATCH_TICKS:-3}"
export AI_JOB_FULL_TRADER_TTL_MINUTES="${AI_JOB_FULL_TRADER_TTL_MINUTES:-20}"
export AI_JOB_FAST_TRADER_TTL_MINUTES="${AI_JOB_FAST_TRADER_TTL_MINUTES:-8}"
export AI_JOB_EVENT_TRADER_TTL_MINUTES="${AI_JOB_EVENT_TRADER_TTL_MINUTES:-5}"
export AI_INTERVAL_ANALYZER_HOURS="${AI_INTERVAL_ANALYZER_HOURS:-6}"
export AI_INTERVAL_FULL_INTERVALS="${AI_INTERVAL_FULL_INTERVALS:-15,20,30,45,60,90}"
export AI_INTERVAL_FAST_INTERVALS="${AI_INTERVAL_FAST_INTERVALS:-5,10,15,20,30}"
export AI_INTERVAL_EVENT_INTERVALS="${AI_INTERVAL_EVENT_INTERVALS:-5,10,15,20,30}"

exec /home/user/trading_venv/bin/python /home/user/ai_dispatcher_interval_analyzer.py "$@"
