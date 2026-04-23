#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"

export AI_RAG_EMBEDDING_PROVIDER=hash
export AI_RAG_HASH_VECTOR_SIZE=64
export AI_RAG_SETUPS_COLLECTION=trade_setups_memory_smoke
export AI_RAG_NEWS_COLLECTION=market_news_memory_smoke
export AI_RAG_MARKET_COLLECTION=market_snapshots_memory_smoke
export AI_RAG_MAX_CHARS=3000
export AI_RAG_SETUPS_LIMIT=3
export AI_RAG_NEWS_LIMIT=3
export AI_RAG_MARKET_LIMIT=2
export AI_RAG_NEWS_MAX_AGE_HOURS=720

cleanup() {
  "$PYTHON_BIN" - <<'PY'
import os
import psycopg2
from hybrid_rag import QdrantMemoryClient

qdrant = QdrantMemoryClient()
qdrant.delete_collection(os.environ["AI_RAG_SETUPS_COLLECTION"])
qdrant.delete_collection(os.environ["AI_RAG_NEWS_COLLECTION"])
qdrant.delete_collection(os.environ["AI_RAG_MARKET_COLLECTION"])

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "market_research"),
    user=os.getenv("DB_USER", "n8n_user"),
    password=os.getenv("DB_PASSWORD", "n8n_db_password"),
)
try:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trading.journal WHERE trader_name = %s", ("__rag_smoke",))
        cur.execute(
            """
            DELETE FROM raw.news_instrument_match
            WHERE news_id IN (
                SELECT news_id
                FROM raw.news_item
                WHERE source = %s AND external_id = %s
            )
            """,
            ("rag_smoke", "hybrid-rag-smoke"),
        )
        cur.execute("DELETE FROM raw.news_item WHERE source = %s AND external_id = %s", ("rag_smoke", "hybrid-rag-smoke"))
    conn.commit()
finally:
    conn.close()
PY
}
trap cleanup EXIT

echo "[1/5] Python compile"
"$PYTHON_BIN" -m py_compile hybrid_rag.py ai_memory_indexer.py ai_paper_trader.py

echo "[2/5] Prepare DB fixtures"
cleanup
"$PYTHON_BIN" - <<'PY'
import json
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
        indicators = {
            "RSI_14": 42.0,
            "ADX_14": 24.0,
            "ATRr_14": 3.2,
            "SMA_20": 100.0,
            "SMA_50": 98.0,
            "VWAP": 101.0,
        }
        cur.execute(
            """
            INSERT INTO trading.journal
                (trader_name, secid, action, quantity, price, reason, model_id, indicators_snapshot, created_at)
            VALUES
                (%s, 'SBER', 'BUY', 10, 100.0, %s, 'smoke-model', %s::jsonb, now() - interval '2 hours'),
                (%s, 'SBER', 'SELL', 10, 103.0, %s, 'smoke-model', %s::jsonb, now() - interval '1 hours')
            """,
            (
                "__rag_smoke",
                "smoke вход по тренду после сжатия волатильности",
                json.dumps(indicators),
                "__rag_smoke",
                "smoke выход по цели",
                json.dumps(indicators),
            ),
        )
        cur.execute(
            """
            INSERT INTO raw.news_item (source, external_id, published_at, title, link, summary, content)
            VALUES (%s, %s, now() - interval '30 minutes', %s, %s, %s, %s)
            RETURNING news_id
            """,
            (
                "rag_smoke",
                "hybrid-rag-smoke",
                "SBER smoke news: повышенный спрос на акции",
                "https://example.invalid/sber-smoke",
                "Позитивная тестовая новость по SBER для проверки Qdrant retrieval.",
                "Позитивная тестовая новость по SBER для проверки Qdrant retrieval.",
            ),
        )
        news_id = cur.fetchone()[0]
    conn.commit()
finally:
    conn.close()
PY

echo "[3/5] Index memory into Qdrant"
"$PYTHON_BIN" ai_memory_indexer.py --mode all --lookback-days 30 --news-lookback-hours 720 --limit 50 --json

echo "[4/5] Retrieve trader RAG context"
"$PYTHON_BIN" - <<'PY'
from hybrid_rag import build_trader_rag_context

ctx = build_trader_rag_context(
    trader_name="Chaos_Bill",
    strategy="Smoke strategy",
    market_features={"SBER": {"p": 103.2, "trend": "trend_up", "ch1d": 1.5, "atr_pct": 2.0}},
    positions=[],
    recent_history=[],
    market_regime="BULL MARKET",
)
print(ctx)
if "RAG_TRADES" not in ctx:
    raise SystemExit("missing trade setup memory")
if "RAG_NEWS" not in ctx:
    raise SystemExit("missing news memory")
if "RAG_MARKET" not in ctx:
    raise SystemExit("missing market snapshot memory")
if "SBER" not in ctx:
    raise SystemExit("missing SBER context")
PY

echo "[5/5] Idempotent indexing skips unchanged documents"
"$PYTHON_BIN" - <<'PY'
import json
from hybrid_rag import index_hybrid_memory

stats = index_hybrid_memory(mode="all", lookback_days=30, news_lookback_hours=720, limit=50)
print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
if stats["setups"]["skipped"] < 1:
    raise SystemExit("expected setup skip on second index")
if stats["news"]["skipped"] < 1:
    raise SystemExit("expected news skip on second index")
if stats["news"].get("keyword_matched", 0) < 1:
    raise SystemExit("expected keyword news match")
if stats["market"]["skipped"] < 1:
    raise SystemExit("expected market snapshot skip on second index")
PY

echo "hybrid RAG smoke tests passed"
