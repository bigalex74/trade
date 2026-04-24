import psycopg2
import os
import requests
import json
from contextlib import closing
from datetime import datetime

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "923741104"

def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
        requests.post(url, json=payload, proxies=proxies, timeout=10)
    except: pass

def run_premarket_check():
    print(f"[{datetime.now().isoformat()}] Running Pre-market Check...")
    report = []
    ready = True
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                # 1. Проверяем БД
                cur.execute("SELECT 1")
                report.append("✅ БД: Онлайн.")
                
                # 2. Проверяем свежесть данных
                cur.execute("SELECT max(updated_at) FROM analytics.trader_market_windows")
                last_update = cur.fetchone()[0]
                if last_update and (datetime.now(last_update.tzinfo) - last_update).total_seconds() < 3600:
                    report.append("✅ Рыночные данные: Актуальны.")
                else:
                    report.append("⚠️ Рыночные данные: Устарели или отсутствуют.")
                    ready = False
                    
                # 3. Проверяем зомби-ордера
                cur.execute("SELECT count(*) FROM trading.orders WHERE status = 'PENDING'")
                pending_count = cur.fetchone()[0]
                if pending_count > 0:
                    report.append(f"⚠️ Зомби-ордера: Найдены ({pending_count} шт). Очистка EOD могла не сработать.")
                else:
                    report.append("✅ Зомби-ордера: Очищены.")

    except Exception as e:
        report.append(f"❌ Ошибка проверки БД: {e}")
        ready = False
        
    status_icon = "🟢" if ready else "🔴"
    status_text = "ГОТОВА К ТОРГАМ" if ready else "ВНИМАНИЕ: ЕСТЬ ПРОБЛЕМЫ"
    
    message = f"{status_icon} <b>PRE-MARKET ОТЧЕТ</b>\nСистема {status_text}\n\n" + "\n".join(report)
    send_telegram(message)
    print("Pre-market check completed.")

if __name__ == "__main__":
    run_premarket_check()
