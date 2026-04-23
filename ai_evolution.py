import psycopg2
import json
import os
import requests
from datetime import datetime, timedelta
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
# TRADERS PERSONALITIES (DNA)
TRADERS_DNA = {
    "VSA_Victor": "VSA Specialist (Volume Spread Analysis). Looks for signs of strength/weakness, climaxes and tests.",
    "Chaos_Bill": "Chaos Theory (Bill Williams). Uses Alligator, Fractals and AO.",
    "Elliott_Alex": "Elliott Wave Expert. Identifies wave structures and targets.",
    "Contrarian_Ricardo": "Mean Reversion / Contrarian. Fades extremes.",
    "Quant_Diana": "Quantitative / Statistical. Focuses on probabilities and ADX.",
    "PriceAction_Nikita": "Pure Price Action. Candles, Levels, Trends.",
    "Passive_Palych": "Safe Dividend / Index investor. Long term bias.",
    "Scalper_Kesha": "Ultra Fast Scalper. High turnover, small targets.",
    "Value_Monya": "Value Investor. Fundamental bias, ignores noise.",
    "Index_Tracker": "Index Mirror. Tracks overall market moves.",
    "Meta_Oracle": "Collective Mind. Analyzes the actions of the other agents."
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram_status(message):
    """Отправляет краткий статус в Telegram."""
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

def get_market_data_for_day():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT secid, window_key, open, high, low, close, volume, indicators, updated_at
        FROM analytics.trader_market_windows
        WHERE updated_at > now() - interval '24 hours'
        ORDER BY secid, updated_at ASC
    """)
    data = {}
    for r in cur.fetchall():
        secid = r[0]
        win = r[1]
        key = f"{secid}:{win}"
        item = data.setdefault(key, {
            "secid": secid,
            "window": win,
            "bars": 0,
            "first_close": None,
            "last_close": None,
            "high": None,
            "low": None,
            "volume": 0.0,
            "last_indicators": {},
            "first_time": None,
            "last_time": None,
        })
        high = float(r[3]) if r[3] is not None else None
        low = float(r[4]) if r[4] is not None else None
        close = float(r[5]) if r[5] is not None else None
        volume = float(r[6] or 0)
        item["bars"] += 1
        item["first_close"] = close if item["first_close"] is None else item["first_close"]
        item["last_close"] = close
        item["high"] = high if item["high"] is None else max(item["high"], high or item["high"])
        item["low"] = low if item["low"] is None else min(item["low"], low or item["low"])
        item["volume"] += volume
        item["last_indicators"] = compact_indicators(r[7] or {})
        item["first_time"] = r[8].isoformat() if item["first_time"] is None else item["first_time"]
        item["last_time"] = r[8].isoformat()
    cur.close(); conn.close()
    summaries = list(data.values())
    for item in summaries:
        first = item.get("first_close") or 0
        last = item.get("last_close") or 0
        item["change_pct"] = round(((last / first) - 1) * 100, 3) if first else 0.0
    return summaries[: int(os.getenv("AI_EVOLUTION_MAX_MARKET_GROUPS", "80"))]

def get_trader_performance():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT trader_name, secid, action, price, reason, model_id, created_at
        FROM trading.journal
        WHERE created_at > now() - interval '24 hours'
        ORDER BY created_at ASC
    """)
    trades = []
    for r in cur.fetchall():
        trades.append({"trader": r[0], "secid": r[1], "act": r[2], "pr": float(r[3]), "rs": r[4], "model": r[5], "time": r[6].isoformat()})
    cur.close(); conn.close()
    summary = {}
    for trade in trades:
        item = summary.setdefault(trade["trader"], {"trade_count": 0, "actions": {}, "secids": {}, "latest": []})
        item["trade_count"] += 1
        item["actions"][trade["act"]] = item["actions"].get(trade["act"], 0) + 1
        item["secids"][trade["secid"]] = item["secids"].get(trade["secid"], 0) + 1
        item["latest"].append({
            "secid": trade["secid"],
            "act": trade["act"],
            "pr": trade["pr"],
            "rs": str(trade["rs"] or "")[:180],
            "time": trade["time"],
        })
    for item in summary.values():
        item["latest"] = item["latest"][-10:]
    return summary

def deep_analyze_and_evolve():
    print("--- STARTING GRANULAR EVOLUTION DEEP DIVE ---")
    test_mode = os.getenv("AI_TEST_MODE", "0") == "1"
    if test_mode:
        market_data = {"SBER": [{"time": datetime.now().isoformat(), "win": "test", "ohlc": [1, 2, 1, 2], "inds": {}}]}
        trader_data = [{"trader": "TestTrader", "secid": "SBER", "act": "BUY", "pr": 1.0, "rs": "smoke test", "model": "test", "time": datetime.now().isoformat()}]
    else:
        market_data = get_market_data_for_day()
        trader_data = get_trader_performance()
    if not market_data and not trader_data:
        print("Evolution skipped: no market/trader data for the last 24 hours.")
        return

    prompt = f"""
    ROLE: Lead Quantitative Auditor & Trading Mentor.
    TASK: METICULOUS retrospective analysis of TODAY'S trading session.
    SYSTEM DNA: {json.dumps(TRADERS_DNA)}
    MARKET DATA: {json.dumps(market_data)}
    ACTUAL TRADES: {json.dumps(trader_data)}
    INSTRUCTIONS: 1. Identify Perfect Path for every asset. 2. Compare actual performance. 3. Propose DNA tuning.
    OUTPUT: Detailed Markdown Report.
    """

    # Модели из рейтинга
    models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    report_md = "Analysis failed."
    report_md = call_ai_markdown_with_fallback(prompt, models, name="Evolution", log_func=print, category="evolution")[0] or report_md

    try:
        if test_mode:
            print("AI_TEST_MODE=1: skipped KB upload and Telegram notification.")
        else:
            if is_low_quality_context(report_md):
                print("Evolution produced no usable report; skipped ALGO KB upload.")
                return
            conn = get_db_connection()
            try:
                candidate_id = create_candidate(
                    conn,
                    source="ai_evolution",
                    title=f"Evolution audit {datetime.now().strftime('%Y-%m-%d')}",
                    candidate_text=report_md,
                    metadata={"kind": "daily_evolution_report", "auto_promote": False},
                )
                print(f"Evolution candidate saved: id={candidate_id}")
            finally:
                conn.close()
            filename = f"deep_dive_{datetime.now().strftime('%Y-%m-%d')}.md"
            with open(filename, "w") as f: f.write(report_md)
            upload_file_to_algo_kb(filename, log_func=print)
            send_telegram_status(f"🧬 <b>ЭВОЛЮЦИОННЫЙ АУДИТ ЗАВЕРШЕН</b>\nОтчет за {datetime.now().strftime('%Y-%m-%d')} загружен в ALGO KB.")
    except Exception as e:
        print(f"Evolution failed: {e}")

if __name__ == "__main__":
    deep_analyze_and_evolve()
