#!/bin/bash
set -u

TRADER="${1:-}"
if [ -z "$TRADER" ]; then
  echo "Usage: $0 TRADER_NAME" >&2
  exit 2
fi

PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/ai_paper_trader.py"
LOG_DIR="/home/user/logs/traders"

mkdir -p "$LOG_DIR"

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
export GEMINI_POOL="${GEMINI_POOL:-moex}"
export AI_COST_GUARD_ENABLED="${AI_COST_GUARD_ENABLED:-1}"
export AI_TRADER_KB_CACHE_SECONDS="${AI_TRADER_KB_CACHE_SECONDS:-900}"
export AI_TRADER_KB_MAX_CHARS="${AI_TRADER_KB_MAX_CHARS:-1200}"
export AI_TRADER_KB_SYMBOLS="${AI_TRADER_KB_SYMBOLS:-6}"
export AI_TRADER_MODELS="${AI_TRADER_MODELS:-gemini-3.1-pro-preview,gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite}"
export AI_MAX_FALLBACKS_TRADER="${AI_MAX_FALLBACKS_TRADER:-5}"
export AI_PROMPT_MAX_CHARS_TRADER="${AI_PROMPT_MAX_CHARS_TRADER:-8000}"
export AI_DEBUG_IO_LOG="${AI_DEBUG_IO_LOG:-1}"
export AI_DEBUG_IO_MAX_CHARS="${AI_DEBUG_IO_MAX_CHARS:-60000}"
export AI_MODEL_COOLDOWN_ENABLED="${AI_MODEL_COOLDOWN_ENABLED:-1}"
export AI_MODEL_COOLDOWN_EXHAUSTED_MINUTES_TRADER="${AI_MODEL_COOLDOWN_EXHAUSTED_MINUTES_TRADER:-60}"
export AI_MODEL_COOLDOWN_TIMEOUT_MINUTES_TRADER="${AI_MODEL_COOLDOWN_TIMEOUT_MINUTES_TRADER:-15}"
export AI_MODEL_FAILURE_THRESHOLD="${AI_MODEL_FAILURE_THRESHOLD:-3}"
export AI_MODEL_HEALTH_WINDOW_MINUTES="${AI_MODEL_HEALTH_WINDOW_MINUTES:-30}"

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Cron tick: $TRADER"
exec "$PYTHON_BIN" "$SCRIPT" "$TRADER"
