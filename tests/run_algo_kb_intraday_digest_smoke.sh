#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"

echo "[1/3] Python compile"
"$PYTHON_BIN" -m py_compile algo_kb_intraday_digest.py algo_kb_client.py hybrid_rag.py

echo "[2/3] Build digest dry-run"
output="$("$PYTHON_BIN" algo_kb_intraday_digest.py --dry-run --top 3 --news-hours 24 --news-limit 5)"
printf '%s\n' "$output" | head -80

echo "[3/3] Validate digest content"
grep -q "MOEX INTRADAY DIGEST" <<<"$output"
grep -q "Режим:" <<<"$output"
grep -q "Фокус:" <<<"$output"
grep -q "Новости" <<<"$output"
grep -q "SBER" <<<"$output"

echo "algo kb intraday digest smoke test passed"
