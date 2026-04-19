#!/usr/bin/env python3
import os
import subprocess
import time
from datetime import datetime, timedelta
import requests

# CONFIG
TRADERS = [
    "VSA_Victor", "Chaos_Bill", "Elliott_Alex", "Contrarian_Ricardo", 
    "Quant_Diana", "PriceAction_Nikita", "Passive_Palych", 
    "Scalper_Kesha", "Value_Monya", "Index_Tracker"
]
LOG_DIR = "/home/user/logs/traders"
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def send_alert(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 <b>WATCHDOG ALERT</b>\n{msg}", "parse_mode": "HTML"}
    try: requests.post(url, json=payload, proxies=PROXIES, timeout=10)
    except: pass

def check_health():
    now = datetime.now()
    # Проверка только в рабочее время MOEX (10:00 - 23:55)
    if now.weekday() > 4 or now.hour < 10 or (now.hour == 23 and now.minute > 55):
        return

    issues = []
    for trader in TRADERS:
        # 1. Проверка процесса воркера
        res = subprocess.run(["pgrep", "-f", f"run_{trader}.sh"], capture_output=True)
        if res.returncode != 0:
            issues.append(f"❌ Воркер {trader} не запущен!")
            continue
            
        # 2. Проверка свежести лога (должен обновляться каждые 5-7 минут)
        log_path = os.path.join(LOG_DIR, f"{trader}.log")
        if not os.path.exists(log_path):
            issues.append(f"❓ Лог {trader} отсутствует!")
            continue
            
        mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
        if now - mtime > timedelta(minutes=15):
            issues.append(f"⏳ Трейдер {trader} молчит более 15 минут!")

    if issues:
        send_alert("\n".join(issues))
    else:
        print(f"[{now.strftime('%H:%M')}] All traders are healthy.")

if __name__ == "__main__":
    check_health()
