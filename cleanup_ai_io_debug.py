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

def cleanup():
    print(f"[{datetime.now().isoformat()}] Starting AI IO Debug Log cleanup...")
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trading.ai_io_debug_log WHERE created_at < now() - interval '7 days'")
                deleted = cur.rowcount
                conn.commit()
                print(f"[{datetime.now().isoformat()}] Cleanup success: deleted {deleted} rows.")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Cleanup FAILED: {e}")

if __name__ == "__main__":
    cleanup()
