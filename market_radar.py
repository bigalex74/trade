import psycopg2
import os
import sys
import json
from decimal import Decimal
from datetime import datetime
from contextlib import closing

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def run_radar_scan():
    print(f"[{datetime.now().isoformat()}] Starting Market Radar Scan...")
    
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                # 1. Ищем внутридневные аномалии (Price/Volume Spikes) через JSONB
                cur.execute("""
                    SELECT secid, five_min_change_pct, 
                           (windows->'5m'->>'volume')::numeric / NULLIF((windows->'5m'->>'volume_sma')::numeric, 0) as vol_ratio
                    FROM analytics.trader_market_context_v
                    WHERE active = TRUE 
                      AND (abs(five_min_change_pct) > 1.5 OR 
                           ((windows->'5m'->>'volume')::numeric / NULLIF((windows->'5m'->>'volume_sma')::numeric, 0)) > 3.0)
                """)
                anomalies = cur.fetchall()
                
                for secid, price_change, vol_ratio in anomalies:
                    if price_change and abs(price_change) > 1.5:
                        cur.execute("INSERT INTO analytics.market_radar_log (secid, event_type, change_pct, volume_ratio) VALUES (%s, 'PRICE_SPIKE', %s, %s)", (secid, price_change, vol_ratio))
                    if vol_ratio and vol_ratio > 3.0:
                        cur.execute("INSERT INTO analytics.market_radar_log (secid, event_type, change_pct, volume_ratio) VALUES (%s, 'VOLUME_SPIKE', %s, %s)", (secid, price_change, vol_ratio))
                    print(f"  [RADAR] Detected anomaly for {secid}: {price_change}% / x{vol_ratio} volume")

                # 2. Утренний скринер (выполняется только в первый час торгов 10:00-11:00)
                now = datetime.now()
                if now.hour == 10:
                    cur.execute("""
                        SELECT secid, day_change_pct
                        FROM analytics.trader_market_context_v
                        WHERE active = TRUE
                        ORDER BY abs(day_change_pct) DESC
                        LIMIT 15
                    """)
                    top_assets = cur.fetchall()
                    for secid, change in top_assets:
                        cur.execute("""
                            INSERT INTO analytics.market_radar_log (secid, event_type, change_pct)
                            VALUES (%s, 'PREMARKET_TOP', %s)
                        """, (secid, change))

            conn.commit()
            print("Radar scan completed.")

    except Exception as e:
        print(f"Radar scan FAILED: {e}")

if __name__ == "__main__":
    run_radar_scan()
