import psycopg2
import json
import os
import sys
import threading
from datetime import datetime, timedelta
from contextlib import closing
from gemini_cli_runner import call_ai_markdown_with_fallback

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
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, proxies=PROXIES, timeout=30)
    except: pass

def run_weekly_evolution():
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    print(f"Starting Weekly DNA Evolution Deep Dive for period {start_date} to {end_date}...")
    
    # 1. Собираем данные за неделю: логи, риски, результаты
    context_data = []
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                # Получаем сводную аналитику за неделю из daily_log_stats
                cur.execute("""
                    SELECT stat_date, report_text, risk_reasons, trader_breakdown
                    FROM trading.daily_log_stats
                    WHERE stat_date BETWEEN %s AND %s
                    ORDER BY stat_date ASC
                """, (start_date, end_date))
                context_data = cur.fetchall()
                
                # Получаем текущие черты трейдеров
                cur.execute("SELECT trader_name, learned_traits, strategy FROM trading.trader_config")
                trader_configs = cur.fetchall()

        if not context_data:
            print("Evolution skipped: no daily log stats found for the week.")
            return

        # 2. Формируем мега-промпт для глубокого анализа
        prompt = f"""
        ROLE: Chief Artificial Intelligence Architect & Quantitative Strategist.
        PERIOD: {start_date} to {end_date}.
        TASK: Conduct a FUNDAMENTAL retrospective of the trading league's performance.
        
        WEEKLY LOGS SUMMARY:
        {json.dumps([{"date": str(r[0]), "risks": r[2]} for r in context_data], ensure_ascii=False)}
        
        CURRENT TRADER DNA:
        {json.dumps([{"name": r[0], "traits": r[1]} for r in trader_configs], ensure_ascii=False)}
        
        OBJECTIVES:
        1. Identify systemic behavioral flaws (e.g., overtrading, ignoring macro trends).
        2. Propose NEW 'Learned Traits' for EACH trader to implement next week.
        3. Explain the WHY behind each change.
        
        OUTPUT: Markdown format with sections:
        ## 🌍 Weekly Market Retrospective
        ## 🧬 DNA Evolution Proposals
        (For each trader: Current Traits -> Proposed Change -> Rationale)
        """

        # Используем Pro модель для самого глубокого анализа (10 мин таймаут)
        models = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]
        report_md, used_model = call_ai_markdown_with_fallback(
            prompt, models, name="WeeklyEvolver", category="evolution"
        )

        if report_md:
            # 3. Сохранение отчета в базу
            with closing(get_db_connection()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO trading.periodic_audits 
                        (audit_type, period_start, period_end, report_text)
                        VALUES ('WEEKLY_EVOLUTION', %s, %s, %s)
                        ON CONFLICT (audit_type, period_end) DO UPDATE SET
                            report_text = EXCLUDED.report_text
                    """, (start_date, end_date, report_md))
                    conn.commit()
            
            # Отправка в Telegram (частями)
            send_telegram(f"🧬 <b>ЕЖЕНЕДЕЛЬНАЯ ИИ-ЭВОЛЮЦИЯ ЗАВЕРШЕНА</b>\nМодель: {used_model}")
            for i in range(0, len(report_md), 4000):
                send_telegram(f"<pre>{report_md[i:i+4000]}</pre>")
                
            print("Weekly DNA Evolution completed.")
        else:
            print("Weekly DNA Evolution failed: no report from AI.")

    except Exception as e:
        print(f"Weekly Evolution FAILED: {e}")

if __name__ == "__main__":
    run_weekly_evolution()
EOF
