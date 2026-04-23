#!/bin/bash
set -u

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
TRADER="${1:-}"
if [ -z "$TRADER" ]; then
  echo "Usage: $0 TRADER_NAME" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
SCRIPT="${PROJECT_DIR}/ai_crypto_trader.py"
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
export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-200}"
export GEMINI_CONCURRENCY="${GEMINI_CONCURRENCY:-2}"
export GEMINI_LOCK_WAIT_SECONDS="${GEMINI_LOCK_WAIT_SECONDS:-240}"
export GEMINI_POOL="${GEMINI_POOL:-crypto}"
export AI_MODEL_RANK_FILE="${AI_MODEL_RANK_FILE:-${PROJECT_DIR}/ai_model_rank.json}"

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Cron tick: $TRADER (Crypto)"
exec "$PYTHON_BIN" "$SCRIPT" "$TRADER"
