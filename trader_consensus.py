import psycopg2
import json
import os
from decimal import Decimal
from contextlib import closing

def load_weighted_consensus(conn, limit=10):
    """
    Загружает топ трейдеров на основе их tuning_score из представления performance
    и возвращает их текущие позиции и недавние действия.
    """
    consensus = []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT trader_name, tuning_score, total_equity, win_rate_pct, trade_count
                FROM trading.trader_performance_v
                WHERE trade_count > 0
                ORDER BY tuning_score DESC
                LIMIT %s
            """, (limit,))
            
            rows = cur.fetchall()
            for r in rows:
                name, score, equity, win_rate, count = r
                consensus.append({
                    "name": name,
                    "score": Decimal(str(score)) if score is not None else Decimal("0"),
                    "equity": Decimal(str(equity)) if equity is not None else Decimal("0"),
                    "win_rate": Decimal(str(win_rate)) if win_rate is not None else Decimal("0"),
                    "trades": count
                })
    except Exception as e:
        print(f"Failed to load consensus: {e}")
        
    return consensus

if __name__ == "__main__":
    # Тестовый запуск
    DB_CONFIG = {
        "host": "localhost",
        "database": "market_research",
        "user": "n8n_user",
        "password": "n8n_db_password",
    }
    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        data = load_weighted_consensus(conn)
        print(f"Loaded {len(data)} high-performing traders for consensus.")
