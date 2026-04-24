import psycopg2
import json
import os
import sys
import requests
import threading
from datetime import datetime, timedelta
from contextlib import closing
from gemini_cli_runner import call_ai_json_with_fallback

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "923741104"
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    def _send():
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        except Exception: pass
    threading.Thread(target=_send, daemon=True).start()

def get_troubled_samples(trader_name, limit=5):
    samples = []
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT prompt_text, response_text, created_at
                    FROM trading.ai_io_debug_log
                    WHERE trader_name = %s 
                      AND (response_text ILIKE '%risk%' OR response_text ILIKE '%confidence": 0%')
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (trader_name, limit))
                for r in cur.fetchall():
                    samples.append({"prompt": r[0], "response": r[1], "time": r[2].isoformat()})
    except Exception as e:
        print(f"Failed to fetch samples: {e}")
    return samples

def tune_trader_prompt(trader_name):
    print(f"--- Self-Tuning Session for {trader_name} ---")
    samples = get_troubled_samples(trader_name)
    if not samples:
        print(f"No troubled samples found for {trader_name}.")
        return None

    meta_prompt = f"""
    ROLE: Prompt Engineer & Trading Quant. TARGET TRADER: {trader_name}
    FAILING SAMPLES: {json.dumps(samples, ensure_ascii=False)[:8000]}
    TASK: 1. Analyze mistakes. 2. Propose SPECIFIC concise addition to 'Learned Traits' to fix it.
    RESPOND ONLY IN JSON: {{"analysis": "...", "proposed_trait": "..."}}
    """
    
    models = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]
    tuning_data, _ = call_ai_json_with_fallback(meta_prompt, models, name=f"Tuner:{trader_name}", category="tuner")
    
    if tuning_data and tuning_data.get("proposed_trait"):
        new_trait = tuning_data["proposed_trait"]
        analysis = tuning_data.get("analysis", "Mistake pattern correction.")
        try:
            with closing(get_db_connection()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE trading.trader_config
                        SET learned_traits = learned_traits || ' ' || %s, updated_at = NOW()
                        WHERE trader_name = %s
                    """, (new_trait, trader_name))
                conn.commit()
            return {"trader": trader_name, "problem": analysis, "fix": new_trait}
        except Exception as e:
            print(f"Failed to save DNA update: {e}")
    return None

if __name__ == "__main__":
    results = []
    if len(sys.argv) > 1:
        res = tune_trader_prompt(sys.argv[1]); 
        if res: results.append(res)
    else:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT trader_name FROM trading.portfolio")
                traders = [r[0] for r in cur.fetchall()]
        for t in traders:
            res = tune_trader_prompt(t)
            if res: results.append(res)
            
    if results:
        report = [
            "🧠 <b>ОТЧЕТ ПО САМООБУЧЕНИЮ ИИ (ВЫХОДНЫЕ)</b>",
            "━━━━━━━━━━━━━━━━━━",
            "✅ <b>ЧТО СДЕЛАНО:</b>",
            f"Проведен анализ {len(results)} трейдеров на основе ошибок прошлой недели.",
            "\n❌ <b>ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ И ИСПРАВЛЕНИЯ:</b>"
        ]
        for r in results:
            report.append(f"\n👤 <b>{r['trader']}</b>:")
            report.append(f"• <u>Проблема</u>: {r['problem'][:200]}...")
            report.append(f"• <u>Исправлено</u>: {r['fix']}")
        send_telegram("\n".join(report))
