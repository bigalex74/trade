import psycopg2
import json
import os
import requests
from datetime import datetime
from algo_kb_client import upload_file_to_algo_kb
from gemini_cli_runner import call_ai_markdown_with_fallback
from ai_context_cache import is_low_quality_context
from strategy_candidate_pipeline import create_candidate

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram_status(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": "923741104", "text": message, "parse_mode": "HTML"}
    try:
        proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
        requests.post(url, json=payload, proxies=proxies, timeout=10)
    except: pass

def compact_indicators(indicators):
    keep_prefixes = (
        "RSI",
        "MACD",
        "ADX",
        "SMA",
        "EMA",
        "VWAP",
        "ATR",
        "AL_",
        "fractal",
        "STOCH",
    )
    compact = {}
    for key, value in (indicators or {}).items():
        if not any(str(key).startswith(prefix) for prefix in keep_prefixes):
            continue
        if isinstance(value, (int, float)):
            compact[key] = round(float(value), 4)
        elif isinstance(value, bool):
            compact[key] = value
    return compact

def get_weekly_high_performers():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT secid, window_key, close, indicators, updated_at
        FROM analytics.trader_market_windows
        WHERE updated_at > now() - interval '7 days'
        ORDER BY secid, updated_at ASC
    """)
    data = {}
    for r in cur.fetchall():
        secid = r[0]
        item = data.setdefault(secid, {
            "bars": 0,
            "first_price": None,
            "last_price": None,
            "high": None,
            "low": None,
            "last_indicators": {},
            "first_time": None,
            "last_time": None,
        })
        price = float(r[2])
        item["bars"] += 1
        item["first_price"] = price if item["first_price"] is None else item["first_price"]
        item["last_price"] = price
        item["high"] = price if item["high"] is None else max(item["high"], price)
        item["low"] = price if item["low"] is None else min(item["low"], price)
        item["last_indicators"] = compact_indicators(r[3] or {})
        item["first_time"] = r[4].isoformat() if item["first_time"] is None else item["first_time"]
        item["last_time"] = r[4].isoformat()
    cur.close(); conn.close()
    summaries = []
    for secid, item in data.items():
        first = item.get("first_price") or 0
        last = item.get("last_price") or 0
        item["secid"] = secid
        item["change_pct"] = round(((last / first) - 1) * 100, 3) if first else 0.0
        summaries.append(item)
    summaries.sort(key=lambda item: abs(item.get("change_pct", 0)), reverse=True)
    return summaries[: int(os.getenv("AI_INCUBATOR_MAX_ASSETS", "80"))]

def synthesize_strategies():
    print("--- STARTING STRATEGY GENETIC INCUBATOR ---")
    test_mode = os.getenv("AI_TEST_MODE", "0") == "1"
    if test_mode:
        history_data = {"SBER": [{"p": 100.0, "inds": {}, "t": datetime.now().isoformat()}]}
    else:
        history_data = get_weekly_high_performers()
    if not history_data:
        print("Incubator skipped: no weekly market data.")
        return

    prompt = f"""
    ROLE: Lead Strategy Architect & Data Scientist.
    TASK: Discover unique profitable patterns and technical rules for EACH asset.
    DATASET: {json.dumps(history_data)}
    OBJECTIVES: 1. Identify 1-2 recurring setups per ticker. 2. Create Alpha Cheat Sheet.
    OUTPUT: Markdown Report.
    """

    models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    alpha_report = "Incubation failed."
    alpha_report = call_ai_markdown_with_fallback(prompt, models, name="Incubator", log_func=print, category="incubator")[0] or alpha_report

    try:
        if test_mode:
            print("AI_TEST_MODE=1: skipped KB upload and Telegram notification.")
        else:
            if is_low_quality_context(alpha_report):
                print("Incubator produced no usable report; skipped ALGO KB upload.")
                return
            conn = get_db_connection()
            try:
                candidate_id = create_candidate(
                    conn,
                    source="ai_genetic_incubator",
                    title=f"Strategy alpha {datetime.now().strftime('%Y-%m-%d')}",
                    candidate_text=alpha_report,
                    metadata={"kind": "alpha_cheat_sheet", "auto_promote": False},
                )
                print(f"Incubator candidate saved: id={candidate_id}")
            finally:
                conn.close()
            filename = f"strategy_alpha_{datetime.now().strftime('%Y-%m-%d')}.md"
            with open(filename, "w") as f: f.write(alpha_report)
            upload_file_to_algo_kb(filename, log_func=print)
            send_telegram_status(f"🧠 <b>ИНКУБАТОР СТРАТЕГИЙ ЗАВЕРШЕН</b>\nStrategic Alpha за {datetime.now().strftime('%Y-%m-%d')} сформирован.")
    except Exception as e:
        print(f"Incubation failed: {e}")

if __name__ == "__main__":
    synthesize_strategies()
