import psycopg2
import json
import os
from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def extract_top_alpha_deals(limit=10):
    print(f"[{datetime.now().isoformat()}] Extracting Top {limit} Alpha Deals of the week...")
    
    deals = []
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                # 1. Находим самые прибыльные закрытые сделки за неделю
                cur.execute("""
                    SELECT id, trader_name, secid, approx_realized_pnl, created_at, price, quantity
                    FROM trading.journal
                    WHERE created_at > now() - interval '7 days'
                      AND is_win = TRUE
                      AND approx_realized_pnl > 0
                    ORDER BY approx_realized_pnl DESC
                    LIMIT %s
                """, (limit,))
                
                rows = cur.fetchall()
                for r in rows:
                    jid, trader, secid, pnl, time, price, qty = r
                    
                    # 2. Ищем рыночный контекст (индикаторы) в момент сделки
                    # Берем самое близкое по времени окно
                    cur.execute("""
                        SELECT indicators 
                        FROM analytics.trader_market_windows
                        WHERE secid = %s AND updated_at <= %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """, (secid, time))
                    
                    ind_row = cur.fetchone()
                    indicators = ind_row[0] if ind_row else {}
                    
                    deals.append({
                        "journal_id": jid,
                        "trader": trader,
                        "secid": secid,
                        "pnl": float(pnl),
                        "price": float(price),
                        "time": time.isoformat(),
                        "market_context": indicators
                    })
                    
        print(f"Successfully extracted {len(deals)} alpha deals.")
        return deals

    except Exception as e:
        print(f"Alpha extraction FAILED: {e}")
        return []

if __name__ == "__main__":
    top_deals = extract_top_alpha_deals()
    if top_deals:
        # Сохраняем во временный файл для следующего этапа (энкодера)
        with open("/tmp/alpha_deals_temp.json", "w") as f:
            json.dump(top_deals, f, ensure_ascii=False)
