import psycopg2
import os
from contextlib import closing
from datetime import datetime

# Позволяет напрямую загрузить рыночный контекст из БД, чтобы сгенерировать эмбеддинги
from market_research_context import load_market_context
from hybrid_rag import build_trader_rag_context

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def warmup_cache():
    print(f"[{datetime.now().isoformat()}] Starting RAG Cache Warmup...")
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            m_ctx = load_market_context(conn)
            # Вызываем функцию RAG для фиктивного трейдера, чтобы закешировать эмбеддинги для новостей и контекста
            print("Warming up embeddings cache...")
            _ = build_trader_rag_context(
                trader_name="System_Warmup", 
                strategy="System Warmup Strategy", 
                market_features=m_ctx, 
                positions=[{"secid": "SBER"}], # Фиктивная позиция
                recent_history=["dummy_history"],
                market_regime="YELLOW"
            )
        print(f"[{datetime.now().isoformat()}] RAG Cache Warmup SUCCESS.")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] RAG Cache Warmup FAILED: {e}")

if __name__ == "__main__":
    warmup_cache()
