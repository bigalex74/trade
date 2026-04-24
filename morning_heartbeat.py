import psycopg2
import os
import sys
import requests
import subprocess
from datetime import datetime
from contextlib import closing
from gemini_cli_runner import call_ai_json_with_fallback

# CONFIG
DB_CONFIG = {"host": os.getenv("DB_HOST", "localhost"), "database": "market_research", "user": os.getenv("DB_USER", "n8n_user"), "password": os.getenv("DB_PASSWORD", "n8n_db_password")}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "923741104"
QDRANT_URL = "http://localhost:6333"
PROXY = "http://127.0.0.1:10808"
PROXIES = {"http": PROXY, "https": PROXY}

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, proxies=PROXIES, timeout=10)
    except: pass

def check_infra():
    checks = []
    # 1. Пинг прокси
    try:
        requests.get("https://google.com", proxies=PROXIES, timeout=5)
        checks.append(("Proxy Connection", True))
    except Exception as e: 
        print(f"Proxy check failed: {e}")
        checks.append(("Proxy Connection", False))
    
    # 2. Пинг Qdrant
    try:
        requests.get(f"{QDRANT_URL}/collections", timeout=5)
        checks.append(("Qdrant Vector DB", True))
    except Exception as e:
        print(f"Qdrant check failed: {e}")
        checks.append(("Qdrant Vector DB", False))
    
    # 3. Gemini API (тестовый вызов)
    try:
        # Пробуем несколько моделей для надежности теста
        test_models = ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
        res, used_model = call_ai_json_with_fallback("Reply ONLY with {'status': 'ok'}", models=test_models, name="Heartbeat", category="audit")
        checks.append((f"Gemini API ({used_model or 'No Model'})", res is not None and res.get("status") == "ok"))
    except Exception as e:
        print(f"Gemini check failed: {e}")
        checks.append(("Gemini API (All models failed)", False))

    # 4. БД Консистентность
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM trading.portfolio")
                checks.append(("PostgreSQL Storage", True))
    except Exception as e:
        print(f"DB check failed: {e}")
        checks.append(("PostgreSQL Storage", False))
    
    return checks

def run_heartbeat():
    print(f"[{datetime.now().isoformat()}] Starting Morning Heartbeat...")
    checks = check_infra()
    
    for name, status in checks:
        print(f"CHECK: {name} -> {'OK' if status else 'FAIL'}")
        
    all_ok = all(c[1] for c in checks)
    print(f"ALL_OK status: {all_ok}")
    
    # Записываем статус в БД для диспетчера
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE trading.system_status SET value = %s, updated_at = NOW() WHERE key = 'system_ready'", (all_ok,))
            conn.commit()
    except Exception as e:
        print(f"Failed to update system_status: {e}")
        all_ok = False

    # Формируем отчет
    icon = "🍏" if all_ok else "🍎"
    report = [f"{icon} <b>MORNING SELF-TEST</b>\n━━━━━━━━━━━━━━━━━━"]
    for name, status in checks:
        report.append(f"{'✅' if status else '❌'} {name}")
    
    if not all_ok:
        report.append("\n🚨 <b>ВНИМАНИЕ: СИСТЕМА ЗАБЛОКИРОВАНА</b>")
        report.append("Торги не начнутся до устранения ошибок.")
    else:
        report.append("\n🟢 Система в норме. Готова к открытию MOEX.")
        
    send_telegram("\n".join(report))
    print("Heartbeat completed.")
    if not all_ok: sys.exit(1)

if __name__ == "__main__":
    run_heartbeat()
