#!/usr/bin/env python3
import os
import psycopg2
from datetime import datetime, timedelta
import requests

# CONFIG
DB_CONFIG = {
    "host": os.getenv("AI_JOBS_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("AI_JOBS_DB_NAME", "market_research"),
    "user": os.getenv("AI_JOBS_DB_USER", os.getenv("DB_USER", "n8n_user")),
    "password": os.getenv("AI_JOBS_DB_PASSWORD", os.getenv("DB_PASSWORD", "n8n_db_password")),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): 
    return psycopg2.connect(**DB_CONFIG)

def send_alert(msg):
    if not TELEGRAM_TOKEN:
        print(f"DEBUG ALERT (No Token):\n{msg}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 <b>АЛЕРТ WATCHDOG: ОЧЕРЕДЬ ЗАДАЧ</b>\n{msg}", "parse_mode": "HTML"}
    try: 
        requests.post(url, json=payload, proxies=PROXIES, timeout=10)
    except Exception as e: 
        print(f"Failed to send Telegram alert: {e}")

def check_jobs_health():
    now = datetime.now()
    issues = []
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Failed or Stale jobs in the last 15 minutes
        cur.execute("""
            SELECT job_type, trader_name, status, count(*), max(error) 
            FROM trading.ai_jobs 
            WHERE status IN ('failed', 'stale') 
              AND updated_at > NOW() - INTERVAL '15 minutes'
            GROUP BY job_type, trader_name, status
        """)
        failed_jobs = cur.fetchall()
        for row in failed_jobs:
            name = row[1] or row[0]
            error_preview = (row[4][:50] + "...") if row[4] and len(row[4]) > 50 else row[4]
            issues.append(f"❌ <b>{row[3]}x {row[2].upper()}</b> for {name}\n   <i>{error_preview}</i>")

        # 2. Jobs stuck in 'running' for more than 15 mins
        cur.execute("""
            SELECT job_type, trader_name, EXTRACT(EPOCH FROM (NOW() - started_at))/60
            FROM trading.ai_jobs
            WHERE status = 'running' AND started_at < NOW() - INTERVAL '15 minutes'
        """)
        stuck_running = cur.fetchall()
        for row in stuck_running:
            name = row[1] or row[0]
            issues.append(f"⏳ <b>STUCK:</b> {name} running for {row[2]:.0f} mins")

        # 3. Queue backlog (if queue size > 20 and not processing fast enough)
        cur.execute("SELECT count(*) FROM trading.ai_jobs WHERE status = 'queued'")
        queued_count = cur.fetchone()[0]
        if queued_count > 20:
            issues.append(f"⚠️ <b>QUEUE BACKLOG:</b> {queued_count} jobs waiting in queue!")

        cur.close()
        conn.close()
    except Exception as e:
        issues.append(f"🔌 <b>DB ERROR:</b> Watchdog cannot connect to DB: {e}")

    if issues:
        send_alert("\n".join(issues))
    else:
        print(f"[{now.strftime('%H:%M')}] All AI Jobs are healthy and processing normally.")

if __name__ == "__main__":
    check_jobs_health()
