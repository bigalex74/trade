#!/usr/bin/env python3
import os
import subprocess
import time
from datetime import datetime, timedelta
import requests

# CONFIG
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRADERS = [
    "VSA_Victor", "Chaos_Bill", "Elliott_Alex", "Contrarian_Ricardo", 
    "Quant_Diana", "PriceAction_Nikita", "Passive_Palych", 
    "Scalper_Kesha", "Value_Monya", "Index_Tracker"
]
LOG_DIR = "/home/user/logs/traders"
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
MANAGE_SCRIPT = os.getenv("MANAGE_TRADERS_SCRIPT", os.path.join(BASE_DIR, "manage_traders.sh"))

def send_alert(msg):
    if not TELEGRAM_TOKEN:
        print(f"ТЕСТОВОЕ УВЕДОМЛЕНИЕ (нет токена/локальный запуск):\n{msg}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"<b>СИСТЕМНЫЙ МОНИТОР ТРЕЙДЕРОВ</b>\n{msg}", "parse_mode": "HTML"}
    try: requests.post(url, json=payload, proxies=PROXIES, timeout=10)
    except Exception as e: print(f"Failed to send Telegram alert: {e}")

def restart_trader(trader):
    print(f"[AUTO-RECOVERY] Attempting to restart {trader}...")
    try:
        # Убиваем старый зависший процесс питона, если он остался
        subprocess.run(["pkill", "-f", f"ai_paper_trader.py {trader}"])
        # Запускаем трейдера через менеджер
        res = subprocess.run(["bash", MANAGE_SCRIPT, "start", trader], capture_output=True, text=True)
        print(f"[AUTO-RECOVERY] Output: {res.stdout.strip()}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to restart {trader}: {e}")
        return False

def check_health():
    now = datetime.now()
    # В тестовом скрипте мы игнорируем рабочие часы MOEX, чтобы проверить логику прямо сейчас
    # if now.weekday() > 4 or now.hour < 10 or (now.hour == 23 and now.minute > 55): return

    issues = []
    restarted = []

    for trader in TRADERS:
        needs_restart = False
        
        # 1. Проверка процесса воркера
        res = subprocess.run(["pgrep", "-f", f"run_{trader}.sh"], capture_output=True)
        if res.returncode != 0:
            issues.append(f"❌ Воркер {trader} не запущен!")
            needs_restart = True
        else:
            # 2. Проверка свежести лога (если воркер запущен, но висит в ожидании API)
            log_path = os.path.join(LOG_DIR, f"{trader}.log")
            if not os.path.exists(log_path):
                issues.append(f"❓ Лог {trader} отсутствует, но процесс жив.")
                needs_restart = True
            else:
                mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
                if now - mtime > timedelta(minutes=15):
                    issues.append(f"⏳ Трейдер {trader} молчит более 15 минут!")
                    needs_restart = True
                    
        # Выполняем авторестарт, если обнаружена проблема
        if needs_restart:
            if restart_trader(trader):
                restarted.append(trader)

    if issues:
        alert_msg = "\n".join(issues)
        if restarted:
            alert_msg += f"\n\n🛠 <b>AUTO-RECOVERY:</b> Успешно отправлена команда на перезапуск: {', '.join(restarted)}"
        send_alert(alert_msg)
        print("Issues found and processed.")
    else:
        print(f"[{now.strftime('%H:%M')}] All traders are healthy and running.")

if __name__ == "__main__":
    check_health()
