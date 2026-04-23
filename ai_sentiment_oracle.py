#!/usr/bin/env python3
import psycopg2
import json
import os
from datetime import datetime
from gemini_cli_runner import call_ai_json_with_fallback

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
    data, _ = call_ai_json_with_fallback(
        prompt,
        ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"],
        name="SentimentOracle",
        log_func=log_event,
        category="sentiment",
    )
    return data

def fresh_tickers(cur, tickers):
    min_interval = int(os.getenv("AI_SENTIMENT_MIN_INTERVAL_MINUTES", "180"))
    if os.getenv("AI_SENTIMENT_FORCE", "0") == "1":
        return set()
    cur.execute(
        """
        SELECT secid
        FROM analytics.market_sentiment
        WHERE secid = ANY(%s)
          AND updated_at > now() - (%s || ' minutes')::interval
        """,
        (tickers, min_interval),
    )
    return {row[0] for row in cur.fetchall()}

def normalize_batch_result(result):
    if not isinstance(result, dict):
        return []
    raw_items = result.get("items") or result.get("sentiments") or []
    if isinstance(raw_items, dict):
        raw_items = [{"secid": secid, **payload} for secid, payload in raw_items.items() if isinstance(payload, dict)]
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        secid = str(item.get("secid") or item.get("ticker") or "").upper().strip()
        if not secid:
            continue
        try:
            score = max(-1.0, min(1.0, float(item.get("score", 0))))
        except Exception:
            score = 0.0
        summary = str(item.get("summary") or "Neutral baseline sentiment.")[:500]
        items.append({"secid": secid, "score": score, "summary": summary})
    return items

def update_sentiment():
    log_event("Starting Sentiment Oracle cycle...")
    conn = get_db_connection(); cur = conn.cursor()
    
    # Топ-активы, которые мы отслеживаем
    TICKERS = ["SBER", "GAZP", "LKOH", "ROSN", "YNDX", "TCSG", "GMKN", "CHMF", "AFLT", "MGNT"]
    max_tickers = int(os.getenv("AI_SENTIMENT_MAX_TICKERS", "0") or "0")
    if max_tickers > 0:
        TICKERS = TICKERS[:max_tickers]

    fresh = fresh_tickers(cur, TICKERS)
    due = [secid for secid in TICKERS if secid not in fresh]
    if not due:
        log_event("Sentiment Oracle skipped: all tracked tickers are fresh.")
        cur.close(); conn.close()
        return

    prompt = f"""
    ROLE: MOEX sentiment analyst.
    TICKERS: {json.dumps(due, ensure_ascii=False)}

    TASK:
    Estimate baseline sentiment for each ticker from -1.0 (bearish) to 1.0 (bullish).
    Use only stable, broad market/fundamental knowledge and the ticker list. Do not browse, do not claim fresh news.
    Keep summaries short and clearly mark uncertainty when current news is unavailable.

    Respond ONLY raw JSON:
    {{"items": [{{"secid": "SBER", "score": 0.0, "summary": "short reason"}}]}}
    """

    result = None if os.getenv("AI_SENTIMENT_DRY_RUN", "0") == "1" else call_ai(prompt)
    items = normalize_batch_result(result)
    if os.getenv("AI_SENTIMENT_DRY_RUN", "0") == "1":
        log_event(f"AI_SENTIMENT_DRY_RUN=1: would update {len(due)} tickers in one batch.")
        cur.close(); conn.close()
        return

    for item in items:
        if item["secid"] not in due:
            continue
        cur.execute("""
            INSERT INTO analytics.market_sentiment (secid, score, summary, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (secid) DO UPDATE SET
                score = EXCLUDED.score,
                summary = EXCLUDED.summary,
                updated_at = NOW()
        """, (item["secid"], item["score"], item["summary"]))
        log_event(f"[SENTIMENT] {item['secid']}: Score {item['score']:+.2f} | {item['summary']}")

    conn.commit(); cur.close(); conn.close()
    log_event(f"Sentiment Oracle cycle complete: updated={len(items)}, due={len(due)}, fresh={len(fresh)}.")

if __name__ == "__main__":
    update_sentiment()
