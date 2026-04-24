import psycopg2
import os
from contextlib import closing
from datetime import datetime

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def cleanup_zombie_orders():
    print(f"[{datetime.now().isoformat()}] Starting EOD Zombie Orders Cleanup...")
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                # Cancel any PENDING order created before today's market open (or older than 12 hours)
                # Since EOD cleanup runs at 23:50, all pending orders from today's session 
                # that haven't been filled should be cancelled to free up capital for tomorrow.
                cur.execute("""
                    UPDATE trading.orders 
                    SET status = 'CANCELLED_EOD',
                        reason = 'Cancelled by End-Of-Day cleanup script',
                        filled_at = clock_timestamp()
                    WHERE status = 'PENDING'
                      AND created_at < clock_timestamp() - interval '1 hour'
                """)
                cancelled_count = cur.rowcount
                conn.commit()
                print(f"[{datetime.now().isoformat()}] Cleanup success: cancelled {cancelled_count} zombie orders.")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Cleanup FAILED: {e}")

if __name__ == "__main__":
    cleanup_zombie_orders()
