#!/usr/bin/env bash
set -euo pipefail

cd /home/user

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
export GEMINI_BIN="/home/user/tests/fake_gemini_cli.py"
export GEMINI_LOCK_PREFIX="tuning_smoke"
export GEMINI_TIMEOUT_SECONDS="${GEMINI_TIMEOUT_SECONDS:-10}"
export AI_COST_GUARD_ENABLED=1
chmod +x "$GEMINI_BIN"

echo "[1/7] Python compile"
"$PYTHON_BIN" -m py_compile \
  market_regime.py \
  trader_consensus.py \
  strategy_candidate_pipeline.py \
  strategy_release_gate.py \
  ai_cost_guard.py \
  gemini_cli_runner.py \
  ai_paper_trader.py \
  ai_evolution.py \
  ai_genetic_incubator.py \
  risk_engine.py

echo "[2/7] Refresh market regime"
"$PYTHON_BIN" /home/user/market_regime.py

echo "[3/7] Validate latest market regime and Meta consensus"
"$PYTHON_BIN" - <<'PY'
from market_regime import compact_regime, get_db_connection, latest_market_regime
from trader_consensus import load_weighted_consensus

conn = get_db_connection()
try:
    regime = compact_regime(latest_market_regime(conn))
    print(regime)
    if not regime or regime["n"] <= 0:
        raise SystemExit("market regime missing")
    consensus = load_weighted_consensus(conn)
    print(consensus[:3])
    if consensus is None:
        raise SystemExit("consensus returned None")
finally:
    conn.close()
PY

echo "[4/7] Sentiment risk rejects strongly negative fresh sentiment"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2
from risk_engine import RiskSettings, review_actions

trader = "__sentiment_risk_smoke"
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
review = review_actions(
    conn,
    trader,
    [{"secid": "SBER", "action": "buy", "reason": "negative sentiment smoke"}],
    {"SBER": {"price": 100.0}},
    {"SBER": {"p": 100.0, "sent_score": -0.8, "sent_age_h": 1.0}},
    settings=RiskSettings(),
)
print(review)
if len(review["rejected"]) != 1 or review["rejected"][0]["reason"] != "negative_sentiment_risk":
    raise SystemExit("expected negative sentiment rejection")
cur.execute("DELETE FROM trading.portfolio WHERE trader_name = %s", (trader,))
conn.commit()
cur.close()
conn.close()
PY

echo "[5/7] Strategy candidate gate blocks promotion without backtest"
candidate_id="$("$PYTHON_BIN" - <<'PY'
from strategy_candidate_pipeline import create_candidate, get_db_connection
conn = get_db_connection()
try:
    print(create_candidate(conn, source="smoke", title="Smoke candidate", candidate_text="Do not promote without backtest.", metadata={"smoke": True}))
finally:
    conn.close()
PY
)"
"$PYTHON_BIN" /home/user/strategy_release_gate.py --candidate-id "$candidate_id" --dry-run | tee /tmp/strategy_gate_smoke.out
if ! grep -q "backtest_required" /tmp/strategy_gate_smoke.out; then
  echo "expected backtest_required release gate block" >&2
  exit 1
fi
"$PYTHON_BIN" - <<PY
from strategy_candidate_pipeline import get_db_connection
conn = get_db_connection()
try:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trading.strategy_candidates WHERE id = %s", ($candidate_id,))
    conn.commit()
finally:
    conn.close()
PY

echo "[6/7] AI debug I/O logging captures prompt and response when explicitly enabled"
"$PYTHON_BIN" - <<'PY'
import os
import psycopg2
from gemini_cli_runner import call_ai_json_with_fallback

os.environ["AI_DEBUG_IO_LOG"] = "1"
os.environ["AI_CALL_SCRIPT"] = "debug_smoke.py"
result, model_id = call_ai_json_with_fallback(
    "Respond ONLY raw JSON: {\"summary\":\"ok\",\"actions\":[]}",
    ["gemini-3-flash-preview"],
    name="DebugSmoke",
    category="general",
)
if not isinstance(result, dict):
    raise SystemExit("fake AI result missing")
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
cur = conn.cursor()
cur.execute("""
    SELECT count(*)
    FROM trading.ai_io_debug_log
    WHERE call_name = 'DebugSmoke'
      AND category = 'general'
      AND prompt_text LIKE 'Respond ONLY raw JSON%%'
""")
count = cur.fetchone()[0]
print("debug rows", count)
if count < 1:
    raise SystemExit("debug I/O row missing")
cur.execute("DELETE FROM trading.ai_io_debug_log WHERE call_name = 'DebugSmoke' AND category = 'general'")
cur.execute("DELETE FROM trading.ai_call_log WHERE call_name = 'DebugSmoke' AND category = 'general'")
conn.commit()
cur.close()
conn.close()
PY

echo "[7/7] Trader dry-run still works with regime/sentiment/consensus hooks"
AI_TRADER_DRY_RUN=1 FAKE_GEMINI_SECID=AFLT FAKE_GEMINI_ACTION=buy RISK_MAX_GROSS_EXPOSURE_PCT=1.0 \
  "$PYTHON_BIN" /home/user/ai_paper_trader.py Chaos_Bill

echo "phase5/phase9 smoke tests passed"
