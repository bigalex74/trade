#!/bin/bash
set -u

LOCK_FILE="/tmp/ai_job_dispatcher.lock"

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

export GEMINI_TRADER_HOME="${GEMINI_TRADER_HOME:-/home/user/gemini-trader-home}"
export GEMINI_WORKDIR="${GEMINI_WORKDIR:-/home/user/gemini-trader-workdir}"
export GEMINI_BIN="${GEMINI_BIN:-/home/user/.nvm/versions/node/v24.14.0/bin/gemini}"
export PATH="$(dirname "$GEMINI_BIN"):${PATH:-/usr/bin:/bin}"
export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-120}"
export GEMINI_CONCURRENCY="${GEMINI_CONCURRENCY:-2}"
export GEMINI_LOCK_WAIT_SECONDS="${GEMINI_LOCK_WAIT_SECONDS:-240}"
export AI_JOB_MAX_WORKERS="${AI_JOB_MAX_WORKERS:-2}"
export AI_JOB_START_BATCH="${AI_JOB_START_BATCH:-1}"
export AI_ENABLE_CRYPTO_AI="${AI_ENABLE_CRYPTO_AI:-0}"
export AI_COST_GUARD_ENABLED="${AI_COST_GUARD_ENABLED:-1}"
export AI_JOB_FULL_WAVE_INTERVAL_MINUTES="${AI_JOB_FULL_WAVE_INTERVAL_MINUTES:-90}"
export AI_JOB_FAST_WAVE_INTERVAL_MINUTES="${AI_JOB_FAST_WAVE_INTERVAL_MINUTES:-10}"
export AI_JOB_EVENT_WAVE_INTERVAL_MINUTES="${AI_JOB_EVENT_WAVE_INTERVAL_MINUTES:-10}"
export AI_JOB_MIN_TRADER_TTL_MINUTES="${AI_JOB_MIN_TRADER_TTL_MINUTES:-20}"
export AI_JOB_FULL_TRADER_TTL_MINUTES="${AI_JOB_FULL_TRADER_TTL_MINUTES:-20}"
export AI_JOB_FAST_TRADER_TTL_MINUTES="${AI_JOB_FAST_TRADER_TTL_MINUTES:-8}"
export AI_JOB_EVENT_TRADER_TTL_MINUTES="${AI_JOB_EVENT_TRADER_TTL_MINUTES:-5}"
export AI_JOB_EVENT_FIVE_MIN_CHANGE_PCT="${AI_JOB_EVENT_FIVE_MIN_CHANGE_PCT:-0.25}"
export AI_JOB_EVENT_HOUR_CHANGE_PCT="${AI_JOB_EVENT_HOUR_CHANGE_PCT:-0.7}"
export AI_JOB_FAST_TRADERS="${AI_JOB_FAST_TRADERS:-Scalper_Kesha,PriceAction_Nikita,VSA_Victor,Quant_Diana,Contrarian_Ricardo,Meta_Oracle}"
export AI_JOB_EVENT_TRADERS="${AI_JOB_EVENT_TRADERS:-Scalper_Kesha,PriceAction_Nikita,VSA_Victor,Quant_Diana,Contrarian_Ricardo,Meta_Oracle}"
export AI_JOB_LOG_IDLE_DECISIONS="${AI_JOB_LOG_IDLE_DECISIONS:-1}"
export AI_JOB_BUDGET_AWARE="${AI_JOB_BUDGET_AWARE:-1}"
export AI_JOB_AI_REQUESTS_PER_TRADER_ESTIMATE="${AI_JOB_AI_REQUESTS_PER_TRADER_ESTIMATE:-2.0}"
export AI_JOB_AI_CALL_RESERVE_TRADER="${AI_JOB_AI_CALL_RESERVE_TRADER:-2}"

DISPATCH_TICKS="${AI_JOB_DISPATCH_TICKS:-3}"
DISPATCH_INTERVAL_SECONDS="${AI_JOB_DISPATCH_INTERVAL_SECONDS:-25}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Previous AI job dispatcher is still running; skipping."
  exit 0
fi

tick=1
while [ "$tick" -le "$DISPATCH_TICKS" ]; do
  /home/user/trading_venv/bin/python /home/user/ai_job_dispatcher.py
  if [ "$tick" -lt "$DISPATCH_TICKS" ]; then
    sleep "$DISPATCH_INTERVAL_SECONDS"
  fi
  tick=$((tick + 1))
done
