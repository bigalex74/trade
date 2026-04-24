import psycopg2
import os
from contextlib import closing
from datetime import datetime, date

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def snapshot_equity():
    print(f"[{datetime.now().isoformat()}] Starting Daily Equity Snapshot...")
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                # Вставляем/обновляем значения эквити для каждого трейдера на конец текущего дня.
                # Используем ON CONFLICT, если скрипт будет запущен дважды
                cur.execute("""
                    INSERT INTO trading.daily_stats (trader_name, stat_date, cash_balance, positions_value, total_value)
                    SELECT e.trader_name,
                           CURRENT_DATE,
                           e.cash_balance,
                           e.positions_value,
                           e.total_equity
                    FROM trading.trader_current_equity_v e
                    ON CONFLICT (trader_name, stat_date) 
                    DO UPDATE SET 
                        cash_balance = EXCLUDED.cash_balance,
                        positions_value = EXCLUDED.positions_value,
                        total_value = EXCLUDED.total_value;
                """)
                snapshot_count = cur.rowcount
                conn.commit()
                print(f"[{datetime.now().isoformat()}] Snapshot success: recorded equity for {snapshot_count} traders.")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Snapshot FAILED: {e}")

if __name__ == "__main__":
    snapshot_equity()
