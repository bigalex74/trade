#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
export GEMINI_BIN="${PROJECT_DIR}/tests/fake_gemini_cli.py"
export GEMINI_LOCK_PREFIX="prompt_compaction_smoke"
export AI_COST_GUARD_ENABLED=1
export AI_RAG_ENABLED=0
export AI_TRADER_DRY_RUN=1
export AI_TRADER_MAX_SYMBOLS=6
export AI_TRADER_MIN_SYMBOLS=4
export AI_PROMPT_TARGET_CHARS_TRADER=5200
export AI_PROMPT_MAX_CHARS_TRADER=8000
export AI_DEBUG_IO_LOG=1

echo "[1/3] Python compile"
"$PYTHON_BIN" -m py_compile trading_feature_contract.py ai_paper_trader.py tests/fake_gemini_cli.py

echo "[2/3] Compact market payload is materially smaller"
"$PYTHON_BIN" - <<'PY'
from market_research_context import load_market_context
from trading_feature_contract import build_trader_market_payload, compact_prompt_market_payload, payload_stats

ctx = load_market_context()
stock = {s: p for s, p in ctx.items() if p.get("engine") == "stock"}
full = build_trader_market_payload(stock, "Scalper_Kesha", max_symbols=6)
compact = compact_prompt_market_payload(full)
full_stats = payload_stats(full)
compact_stats = payload_stats(compact)
print({"full": full_stats, "compact": compact_stats})
if compact_stats["chars"] >= full_stats["chars"] * 0.7:
    raise SystemExit("compact payload did not shrink enough")
if compact_stats["symbols"] != full_stats["symbols"]:
    raise SystemExit("compact payload changed symbol count")
PY

echo "[3/3] Trader prompt stays under target"
"$PYTHON_BIN" ai_paper_trader.py Scalper_Kesha
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT prompt_chars
            FROM trading.ai_call_log
            WHERE trader_name = 'Scalper_Kesha'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        prompt_chars = cur.fetchone()[0]
        print({"prompt_chars": prompt_chars})
        if prompt_chars > 5200:
            raise SystemExit(f"prompt still above target: {prompt_chars}")
finally:
    conn.close()
PY

echo "prompt compaction smoke tests passed"
