import psycopg2
import json
import os
import requests
import threading
from datetime import datetime, timedelta
from contextlib import closing
from algo_kb_client import upload_file_to_algo_kb
from gemini_cli_runner import call_ai_markdown_with_fallback, call_ai_json_with_fallback
from ai_context_cache import is_low_quality_context
from strategy_candidate_pipeline import create_candidate

# CONFIG
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_HOME = os.path.expanduser("~")

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
    """Отправляет краткий статус в Telegram асинхронно."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: return
    def _send():
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": "923741104", "text": message, "parse_mode": "HTML"}
        try:
            proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
            requests.post(url, json=payload, proxies=proxies, timeout=10)
        except Exception: pass
    threading.Thread(target=_send, daemon=True).start()

def compact_indicators(indicators):
    keep_prefixes = ("RSI", "MACD", "ADX", "SMA", "EMA", "VWAP", "ATR", "AL_", "fractal", "STOCH")
    compact = {}
    for key, value in (indicators or {}).items():
        if not any(str(key).startswith(prefix) for prefix in keep_prefixes): continue
        if isinstance(value, (int, float)): compact[key] = round(float(value), 4)
        elif isinstance(value, bool): compact[key] = value
    return compact

def get_market_data_for_day():
    data = {}
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT secid, window_key, open, high, low, close, volume, indicators, updated_at
                    FROM analytics.trader_market_windows
                    WHERE updated_at > now() - interval '24 hours'
                    ORDER BY secid, updated_at ASC
                """)
                for r in cur.fetchall():
                    secid, win = r[0], r[1]; key = f"{secid}:{win}"
                    item = data.setdefault(key, {"secid": secid, "window": win, "bars": 0, "first_close": None, "last_close": None, "high": None, "low": None, "volume": 0.0, "last_indicators": {}, "first_time": None, "last_time": None})
                    high, low, close, volume = float(r[3] or 0), float(r[4] or 0), float(r[5] or 0), float(r[6] or 0)
                    item["bars"] += 1
                    item["first_close"] = close if item["first_close"] is None else item["first_close"]
                    item["last_close"] = close
                    item["high"] = high if item["high"] is None else max(item["high"], high)
                    item["low"] = low if item["low"] is None else min(item["low"], low)
                    item["volume"] += volume
                    item["last_indicators"] = compact_indicators(r[7] or {})
                    item["first_time"] = r[8].isoformat() if item["first_time"] is None else item["first_time"]
                    item["last_time"] = r[8].isoformat()
    except Exception as e:
        print(f"Failed to fetch market data: {e}")
        return []
    summaries = list(data.values())
    for item in summaries:
        first, last = item.get("first_close") or 0, item.get("last_close") or 0
        item["change_pct"] = round(((last / first) - 1) * 100, 3) if first else 0.0
    return summaries[: int(os.getenv("AI_EVOLUTION_MAX_MARKET_GROUPS", "80"))]

def get_trader_performance():
    trades = []
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT trader_name, secid, action, price, reason, model_id, created_at
                    FROM trading.journal WHERE created_at > now() - interval '24 hours' ORDER BY created_at ASC
                """)
                for r in cur.fetchall():
                    trades.append({"trader": r[0], "secid": r[1], "act": r[2], "pr": float(r[3]), "rs": r[4], "model": r[5], "time": r[6].isoformat()})
    except Exception as e:
        print(f"Failed to fetch journal: {e}")
        return {}
    summary = {}
    for trade in trades:
        item = summary.setdefault(trade["trader"], {"trade_count": 0, "actions": {}, "secids": {}, "latest": []})
        item["trade_count"] += 1
        item["actions"][trade["act"]] = item["actions"].get(trade["act"], 0) + 1
        item["secids"][trade["secid"]] = item["secids"].get(trade["secid"], 0) + 1
        item["latest"].append({"secid": trade["secid"], "act": trade["act"], "pr": trade["pr"], "rs": str(trade["rs"] or "")[:180], "time": trade["time"]})
    for item in summary.values(): item["latest"] = item["latest"][-10:]
    return summary

def deep_analyze_and_evolve():
    print("--- STARTING GRANULAR EVOLUTION DEEP DIVE ---")
    market_data = get_market_data_for_day()
    trader_data = get_trader_performance()
    if not market_data and not trader_data: return

    prompt = f"ROLE: Lead Auditor. RETROSPECTIVE: TODAY session. MARKET: {json.dumps(market_data)}. TRADES: {json.dumps(trader_data)}. DNA: {json.dumps(TRADERS_DNA)}. TASK: Identify flaws, propose NEW 'Learned Traits' for EACH trader. OUTPUT: Markdown Report."
    models = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]
    report_md, used_model = call_ai_markdown_with_fallback(prompt, models, name="Evolution", log_func=print, category="evolution")

    if report_md:
        try:
            with closing(get_db_connection()) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO trading.periodic_audits (audit_type, period_start, period_end, report_text) VALUES ('DAILY_EVOLUTION', CURRENT_DATE, CURRENT_DATE, %s) ON CONFLICT (audit_type, period_end) DO UPDATE SET report_text = EXCLUDED.report_text", (report_md,))
                conn.commit()
            
            # 4. AUTO-CLONING LOGIC
            print("Extracting shadow DNA from report...")
            dna_prompt = f"Based on this report, extract ONLY a raw JSON object: {{trader_name: 'specific new learned traits string'}}. Focus only on actionable tuning rules. REPORT: {report_md}"
            dna_json, _ = call_ai_json_with_fallback(dna_prompt, ["gemini-3-flash-preview"], name="DnaExtractor", category="evolution")
            
            if dna_json:
                with closing(get_db_connection()) as conn:
                    with conn.cursor() as cur:
                        for name, dna in dna_json.items():
                            if name in TRADERS_DNA:
                                cur.execute("INSERT INTO trading.shadow_portfolio (trader_name, learned_traits, is_active) VALUES (%s, %s, TRUE) ON CONFLICT (trader_name) DO UPDATE SET learned_traits = EXCLUDED.learned_traits, is_active = TRUE", (name, dna))
                                print(f"Shadow clone updated: {name}")
                    conn.commit()

            send_telegram_status(f"🧬 <b>ЭВОЛЮЦИОННЫЙ АУДИТ ЗАВЕРШЕН</b>\nНовые черты применены к теневым клонам в БД.")
        except Exception as e: print(f"Post-evolution processing failed: {e}")

if __name__ == "__main__":
    deep_analyze_and_evolve()
