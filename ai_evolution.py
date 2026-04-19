#!/usr/bin/env python3
import psycopg2
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

MODEL_RANK_FILE = "/home/user/ai_model_rank.json"
LOG_FILE = "/home/user/logs/ai_evolution.log"

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def call_ai(prompt):
    with open(MODEL_RANK_FILE) as f:
        # Используем самую мощную модель для анализа (первую в списке)
        model = json.load(f)['models'][0]['id']
    
    cmd = ["gemini", "-p", prompt, "--model", model, "--output-format", "json", "--approval-mode", "yolo"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            return None
        out_text = json.loads(res.stdout).get("response", "")
        if "```json" in out_text: out_text = out_text.split("```json")[1].split("```")[0]
        return json.loads(out_text)
    except Exception as e:
        log(f"AI Call Error: {e}")
        return None

def evolve_trader(trader_name):
    log(f"Starting evolution for {trader_name}...")
    conn = get_db_connection(); cur = conn.cursor()
    
    # 1. Загружаем сделки за последние 24 часа
    cur.execute("""
        SELECT secid, action, quantity, price, reason, created_at
        FROM trading.journal
        WHERE trader_name = %s AND created_at > NOW() - INTERVAL '24 hours'
        ORDER BY created_at ASC
    """, (trader_name,))
    trades = cur.fetchall()
    
    if not trades:
        log(f"No trades for {trader_name} in last 24h. Skipping.")
        cur.close(); conn.close()
        return

    # 2. Загружаем текущие черты и PnL
    cur.execute("SELECT learned_traits FROM trading.trader_config WHERE trader_name = %s", (trader_name,))
    current_traits = cur.fetchone()[0]
    
    # Формируем отчет для AI
    history_str = ""
    for t in trades:
        history_str += f"- {t[5].strftime('%H:%M')} {t[1]} {t[0]} @{t[3]}. Reason: {t[4]}\n"

    prompt = f"""
    Act as a Senior Trading Auditor. Analyze the daily performance of AI Trader: {trader_name}.
    Current Learned Traits (Memory): {current_traits}
    
    Last 24h Trades:
    {history_str}
    
    Your task:
    1. Identify behavioral patterns (e.g. "Too aggressive in downtrend", "Ignored RSI overbought").
    2. Formulate 2-3 NEW concise 'learned_traits' (short instructions in Russian) to improve performance.
    3. Keep existing traits if they are still valid, but refine them.
    
    Respond ONLY raw JSON: {{"analysis": "short summary", "new_traits": "string with instructions"}}
    """
    
    evolution = call_ai(prompt)
    if evolution and "new_traits" in evolution:
        new_traits = evolution["new_traits"]
        cur.execute("UPDATE trading.trader_config SET learned_traits = %s, updated_at = NOW() WHERE trader_name = %s", (new_traits, trader_name))
        log(f"Evolution complete for {trader_name}. New traits: {new_traits[:100]}...")
    
    conn.commit(); cur.close(); conn.close()

def main():
    traders = [
        "VSA_Victor", "Chaos_Bill", "Elliott_Alex", "Contrarian_Ricardo", 
        "Quant_Diana", "PriceAction_Nikita", "Passive_Palych", 
        "Scalper_Kesha", "Value_Monya", "Index_Tracker"
    ]
    for t in traders:
        try:
            evolve_trader(t)
        except Exception as e:
            log(f"Error evolving {t}: {e}")

if __name__ == "__main__":
    main()
