#!/usr/bin/env python3
import psycopg2
import json
import os
import subprocess
from datetime import datetime

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

LOG_FILE = "/home/user/logs/ai_sentiment.log"

def log_event(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def call_ai(prompt):
    cmd = ["gemini", "-p", prompt, "--model", "gemini-3-flash-preview", "--output-format", "json", "--approval-mode", "yolo"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            raw_out = res.stdout
            if "```json" in raw_out:
                raw_out = raw_out.split("```json")[1].split("```")[0]
            data = json.loads(raw_out)
            resp_text = data.get("response", "")
            if isinstance(resp_text, str) and resp_text.strip().startswith("{"):
                return json.loads(resp_text)
            return data
    except Exception as e:
        log_event(f"AI Call Error: {e}")
    return None

def fetch_rss_news(ticker):
    # Упрощенная эмуляция сбора новостей через RSS-фиды (БКС, Смарт-Лаб)
    # В реальной реализации здесь будет запрос к SearXNG или RSS
    # Для стабильности мы генерируем запрос к AI на анализ последних трендов из его базы знаний
    return f"Найди последние новости и оценки по акциям {ticker} на Московской бирже (сегодня). Если новостей нет, оцени общую фундаментальную картину."

def update_sentiment():
    log_event("Starting Sentiment Oracle cycle...")
    conn = get_db_connection(); cur = conn.cursor()
    
    # Топ-активы, которые мы отслеживаем
    TICKERS = ["SBER", "GAZP", "LKOH", "ROSN", "YNDX", "TCSG", "GMKN", "CHMF", "AFLT", "MGNT"]
    
    for secid in TICKERS:
        news_query = fetch_rss_news(secid)
        prompt = f"""
        Act as a Wall Street Sentiment Oracle. 
        Analyze the current fundamental and news background for the Russian stock: {secid}.
        News context: {news_query}
        
        TASK:
        1. Score the current sentiment from -1.0 (Very Bearish, bad news, panic) to 1.0 (Very Bullish, great reports, growth).
        2. Provide a 1-sentence summary of why.
        
        Respond ONLY raw JSON: {{"score": float, "summary": "string"}}
        """
        
        result = call_ai(prompt)
        if result and "score" in result:
            score = float(result["score"])
            summary = result.get("summary", "No summary")
            
            cur.execute("""
                INSERT INTO analytics.market_sentiment (secid, score, summary, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (secid) DO UPDATE SET
                    score = EXCLUDED.score,
                    summary = EXCLUDED.summary,
                    updated_at = NOW()
            """, (secid, score, summary))
            
            log_event(f"[SENTIMENT] {secid}: Score {score:+.2f} | {summary}")
            
    conn.commit(); cur.close(); conn.close()
    log_event("Sentiment Oracle cycle complete.")

if __name__ == "__main__":
    update_sentiment()
