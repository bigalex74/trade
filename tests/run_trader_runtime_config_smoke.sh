#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

echo "[1/2] Проверка runtime-настроек трейдеров"

grep -q 'export GEMINI_CONCURRENCY="${GEMINI_CONCURRENCY:-1}"' run_ai_trader_once.sh
grep -q 'export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-200}"' run_ai_trader_once.sh
grep -q 'export GEMINI_ATTEMPT_TIMEOUT_SECONDS_TRADER="${GEMINI_ATTEMPT_TIMEOUT_SECONDS_TRADER:-60}"' run_ai_trader_once.sh
grep -q 'export AI_MODEL_COOLDOWN_TIMEOUT_MINUTES_TRADER="${AI_MODEL_COOLDOWN_TIMEOUT_MINUTES_TRADER:-0}"' run_ai_trader_once.sh
grep -q 'export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-200}"' run_ai_job_dispatcher.sh
grep -q 'export GEMINI_CONCURRENCY="${GEMINI_CONCURRENCY:-1}"' run_ai_job_dispatcher.sh
grep -q 'export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-200}"' run_ai_crypto_trader_once.sh

echo "[2/2] Проверка отсутствия Ollama fallback для MOEX"
grep -q 'include_ollama=False' ai_paper_trader.py

echo "trader runtime config smoke test passed"
