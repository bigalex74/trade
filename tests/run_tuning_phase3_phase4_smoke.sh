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
  risk_engine.py \
  trading_feature_contract.py \
  ai_paper_trader.py \
  order_matching_engine.py \
  tests/fake_gemini_cli.py

echo "[2/6] Direct risk engine checks"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2
from risk_engine import RiskSettings, review_actions

trader = "__risk_smoke"
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
cur = conn.cursor()
cur.execute("DELETE FROM trading.orders WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.journal WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.position WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.portfolio WHERE trader_name = %s", (trader,))
cur.execute("INSERT INTO trading.portfolio (trader_name, cash_balance) VALUES (%s, %s)", (trader, 10000))
conn.commit()

settings = RiskSettings(max_actions_per_decision=2, max_actions_per_trader_day=3)
prices = {"SBER": {"price": 100.0}, "GAZP": {"price": 50.0}}
features = {"SBER": {"p": 100.0, "atr_pct": 2.0}, "GAZP": {"p": 50.0}}
review = review_actions(conn, trader, [{"secid": "SBER", "action": "buy", "reason": "ok"}], prices, features, settings=settings)
print(review)
if len(review["accepted"]) != 1 or review["accepted"][0]["quantity"] < 1:
    raise SystemExit("expected one accepted buy")

review = review_actions(conn, trader, [{"secid": "SBER", "action": "short", "reason": "bad"}], prices, features, settings=settings)
if len(review["rejected"]) != 1 or review["rejected"][0]["reason"] != "short_book_not_enabled":
    raise SystemExit("expected short rejection")

cur.execute("DELETE FROM trading.portfolio WHERE trader_name = %s", (trader,))
conn.commit()
cur.close()
conn.close()
PY

echo "[3/6] Trader dry-run creates no orders and accepts a sane buy"
before_orders="$("$PYTHON_BIN" - <<'PY'
import os, psycopg2
conn = psycopg2.connect(host=os.getenv("DB_HOST", "localhost"), database=os.getenv("DB_NAME", "market_research"), user=os.getenv("DB_USER", "n8n_user"), password=os.getenv("DB_PASSWORD", "n8n_db_password"))
cur = conn.cursor()
cur.execute("SELECT count(*) FROM trading.orders WHERE trader_name = 'Chaos_Bill'")
print(cur.fetchone()[0])
cur.close(); conn.close()
PY
)"
out="$(RISK_MAX_GROSS_EXPOSURE_PCT=1.0 FAKE_GEMINI_SECID=AFLT FAKE_GEMINI_ACTION=buy "$PYTHON_BIN" "${PROJECT_DIR}/ai_paper_trader.py" Chaos_Bill)"
echo "$out"
after_orders="$("$PYTHON_BIN" - <<'PY'
import os, psycopg2
conn = psycopg2.connect(host=os.getenv("DB_HOST", "localhost"), database=os.getenv("DB_NAME", "market_research"), user=os.getenv("DB_USER", "n8n_user"), password=os.getenv("DB_PASSWORD", "n8n_db_password"))
cur = conn.cursor()
cur.execute("SELECT count(*) FROM trading.orders WHERE trader_name = 'Chaos_Bill'")
print(cur.fetchone()[0])
cur.close(); conn.close()
PY
)"
if [ "$before_orders" != "$after_orders" ]; then
  echo "orders mutated during trader dry-run" >&2
  exit 1
fi
if ! grep -q "Risk review: accepted=1 rejected=0" <<<"$out"; then
  echo "expected accepted=1 rejected=0 in trader dry-run" >&2
  exit 1
fi

echo "[4/6] Trader dry-run rejects short actions"
out="$(FAKE_GEMINI_SECID=SBER FAKE_GEMINI_ACTION=short "$PYTHON_BIN" "${PROJECT_DIR}/ai_paper_trader.py" Chaos_Bill)"
echo "$out"
if ! grep -q "Risk review: accepted=0 rejected=1" <<<"$out"; then
  echo "expected accepted=0 rejected=1 for short action" >&2
  exit 1
fi

echo "[5/6] Matching engine dry-run rolls back fills"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2

trader = "__matching_smoke"
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
cur = conn.cursor()
cur.execute("DELETE FROM trading.orders WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.journal WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.position WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.portfolio WHERE trader_name = %s", (trader,))
cur.execute("INSERT INTO trading.portfolio (trader_name, cash_balance) VALUES (%s, %s)", (trader, 100000))
cur.execute("SELECT current_price FROM analytics.trader_market_context_v WHERE secid = 'SBER' AND current_price IS NOT NULL LIMIT 1")
price = float(cur.fetchone()[0])
cur.execute(
    """
    INSERT INTO trading.orders (trader_name, secid, order_type, quantity, target_price, status, model_id, reason)
    VALUES (%s, 'SBER', 'limit_buy', 1, %s, 'PENDING', 'smoke', 'matching dry-run smoke')
    """,
    (trader, price * 1.01),
)
conn.commit()
cur.close()
conn.close()
PY
MATCHING_DRY_RUN=1 "$PYTHON_BIN" "${PROJECT_DIR}/order_matching_engine.py"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2

trader = "__matching_smoke"
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
cur = conn.cursor()
cur.execute("SELECT status, quantity FROM trading.orders WHERE trader_name = %s", (trader,))
rows = cur.fetchall()
print(rows)
if rows != [("PENDING", 1)]:
    raise SystemExit("matching dry-run mutated order")
cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = %s", (trader,))
if cur.fetchone()[0] != 0:
    raise SystemExit("matching dry-run wrote journal")
cur.execute("DELETE FROM trading.orders WHERE trader_name = %s", (trader,))
cur.execute("DELETE FROM trading.portfolio WHERE trader_name = %s", (trader,))
conn.commit()
cur.close()
conn.close()
PY

echo "[6/6] Existing phase1/phase2 smoke still passes"
"${PROJECT_DIR}/tests/run_tuning_phase1_phase2_smoke.sh"

echo "phase3/phase4 smoke tests passed"
