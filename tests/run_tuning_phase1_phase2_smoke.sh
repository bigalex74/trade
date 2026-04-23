#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
export GEMINI_BIN="${PROJECT_DIR}/tests/fake_gemini_cli.py"
export GEMINI_LOCK_PREFIX="tuning_smoke"
export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-10}"
export AI_COST_GUARD_ENABLED=1
export AI_TRADER_DRY_RUN=1
export AI_TRADER_MAX_SYMBOLS="${AI_TRADER_MAX_SYMBOLS:-8}"
export AI_TRADER_KB_CACHE_SECONDS="${AI_TRADER_KB_CACHE_SECONDS:-900}"

chmod +x "$GEMINI_BIN"

echo "[1/6] Python compile"
"$PYTHON_BIN" -m py_compile \
  trading_metrics_setup.py \
  trading_feature_contract.py \
  ai_paper_trader.py \
  ai_backtester.py \
  gemini_cli_runner.py \
  ai_cost_guard.py

echo "[2/6] Install/refresh metrics views"
"$PYTHON_BIN" "${PROJECT_DIR}/trading_metrics_setup.py"

echo "[3/6] Validate metrics views"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
cur = conn.cursor()
checks = {
    "trading.trader_current_equity_v": 1,
    "trading.trader_performance_v": 1,
    "trading.benchmark_symbols_v": 1,
    "trading.market_benchmark_v": 3,
}
for view, minimum in checks.items():
    cur.execute(f"SELECT count(*) FROM {view}")
    count = cur.fetchone()[0]
    print(f"{view}: {count}")
    if count < minimum:
        raise SystemExit(f"{view} expected >= {minimum}, got {count}")
cur.close()
conn.close()
PY

echo "[4/6] Validate feature contract payload"
"$PYTHON_BIN" - <<'PY'
from market_research_context import load_market_context
from trading_feature_contract import build_trader_market_payload, payload_stats

ctx = load_market_context()
stock = {s: p for s, p in ctx.items() if p.get("engine") == "stock"}
payload = build_trader_market_payload(stock, "Chaos_Bill", max_symbols=8)
stats = payload_stats(payload)
print(stats)
if stats["symbols"] <= 0:
    raise SystemExit("feature payload is empty")
if stats["chars"] > 6000:
    raise SystemExit(f"feature payload too large: {stats['chars']}")
sample = next(iter(payload.values()))
for key in ("p", "ch1d", "trend"):
    if key not in sample:
        raise SystemExit(f"missing expected feature key: {key}")
PY

echo "[5/6] MOEX trader dry-run with fake Gemini"
before="$("$PYTHON_BIN" - <<'PY'
import os
import psycopg2
conn = psycopg2.connect(host=os.getenv("DB_HOST", "localhost"), database=os.getenv("DB_NAME", "market_research"), user=os.getenv("DB_USER", "n8n_user"), password=os.getenv("DB_PASSWORD", "n8n_db_password"))
cur = conn.cursor()
cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = 'Chaos_Bill'")
print(cur.fetchone()[0])
cur.close(); conn.close()
PY
)"
"$PYTHON_BIN" "${PROJECT_DIR}/ai_paper_trader.py" Chaos_Bill
after="$("$PYTHON_BIN" - <<'PY'
import os
import psycopg2
conn = psycopg2.connect(host=os.getenv("DB_HOST", "localhost"), database=os.getenv("DB_NAME", "market_research"), user=os.getenv("DB_USER", "n8n_user"), password=os.getenv("DB_PASSWORD", "n8n_db_password"))
cur = conn.cursor()
cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = 'Chaos_Bill'")
print(cur.fetchone()[0])
cur.close(); conn.close()
PY
)"
echo "Chaos_Bill journal before=$before after=$after"
if [ "$before" != "$after" ]; then
  echo "journal mutated during dry-run" >&2
  exit 1
fi

echo "[6/6] Backtester dry-run"
"$PYTHON_BIN" "${PROJECT_DIR}/ai_backtester.py" \
  --start 2026-04-15 --end 2026-04-21 \
  --trader Chaos_Bill \
  --max-days 3 --max-symbols 5 --batch-days 2

echo "phase1/phase2 smoke tests passed"
