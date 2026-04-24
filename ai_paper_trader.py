#!/usr/bin/env python3
import psycopg2, json, os, requests, sys, html, threading, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from contextlib import closing

# Настройка буферизации для логов
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

from market_research_context import build_price_snapshot, compact_context_payload, load_market_context
from gemini_cli_runner import call_ai_json_with_fallback
from hybrid_rag import build_trader_rag_context
from risk_engine import RiskSettings, review_actions, _decimal
from trader_consensus import load_weighted_consensus
from trading_feature_contract import build_trader_market_payload, compact_prompt_market_payload, payload_stats

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL_RANK_FILE = os.getenv("AI_MODEL_RANK_FILE", os.path.join(BASE_DIR, "ai_model_rank.json"))
# Логи теперь строятся динамически относительно расположения проекта
LOG_DIR = os.getenv("AI_LOG_DIR", os.path.join(os.path.dirname(BASE_DIR), "logs"))
LOG_FILE = os.path.join(LOG_DIR, "ai_trader.log")
INITIAL_CAPITAL = Decimal("10000.0")

TRADERS_DATA = {
    "VSA_Victor": {"strategy": "VSA Specialist (Volume Spread Analysis). Look for sign of strength/weakness, climaxes and tests.", "query": "VSA trading methods"},
    "Chaos_Bill": {"strategy": "Chaos Theory (Bill Williams). Use Alligator, Fractals and AO.", "query": "Bill Williams trading strategy"},
    "Elliott_Alex": {"strategy": "Elliott Wave Expert. Identify wave structures and targets.", "query": "Elliott wave analysis"},
    "Contrarian_Ricardo": {"strategy": "Mean Reversion / Contrarian. Fades extremes.", "query": "Contrarian trading patterns"},
    "Quant_Diana": {"strategy": "Quantitative / Statistical. Focus on probabilities and ADX.", "query": "Quantitative trading signals"},
    "PriceAction_Nikita": {"strategy": "Pure Price Action. Candles, Levels, Trends.", "query": "Price action trading setups"},
    "Passive_Palych": {"strategy": "Safe Dividend / Index investor. Long term bias.", "query": "Dividend growth investing"},
    "Scalper_Kesha": {"strategy": "Ultra Fast Scalper. High turnover, small targets.", "query": "Intraday scalping techniques"},
    "Value_Monya": {"strategy": "Value Investor. Fundamental bias, ignores noise.", "query": "Value investing metrics"},
    "Index_Tracker": {"strategy": "Index Mirror. Tracks overall MOEX market moves.", "query": "Index tracking strategy"},
    "Meta_Oracle": {"strategy": "Collective Mind. You analyze the actions of the other 10 AI agents. You buy ONLY when multiple independent algorithms buy the same asset.", "query": "Ensemble trading strategies and consensus"}
}

def log_event(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    def _send():
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
            requests.post(url, json=payload, proxies=proxies, timeout=15)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

def log_analytics_event(trader_name, event_type, data):
    analytics_dir = os.path.join(LOG_DIR, "analytics")
    os.makedirs(analytics_dir, exist_ok=True)
    filename = os.path.join(analytics_dir, f"events_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    event = {"timestamp": datetime.now().isoformat(), "trader": trader_name, "event": event_type, "data": data}
    try:
        with open(filename, "a") as f:
            # Преобразование Decimal в float для JSON
            def default_json(obj):
                if isinstance(obj, Decimal): return float(obj)
                raise TypeError
            f.write(json.dumps(event, ensure_ascii=False, default=default_json) + "\n")
    except Exception: pass

def format_money(val): return f"{float(val):,.2f}"
def format_pct(val): return f"{float(val):+.2f}%"
def format_trade_time(dt): return dt.strftime("%H:%M")

def get_latest_ai_failure_reason(trader_name):
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT model_id, status, error FROM trading.ai_call_log WHERE trader_name = %s ORDER BY id DESC LIMIT 1", (trader_name,))
                row = cur.fetchone()
                if row: return f"модель {row[0]} {row[1]}. {row[2] or ''}"
    except: pass
    return "неизвестная техническая ошибка"

def compact_positions_for_prompt(positions):
    return [{"s": p["secid"], "q": p["qty"], "pnl": p["pnl_pct"]} for p in positions]

def compact_macro_for_prompt(data):
    if not data: return {}
    return {"usd": data.get("p"), "change": data.get("change_pct")}

def compact_regime_label(label):
    if not label: return "UNKNOWN"
    if "BULL" in label: return "BULL"
    if "BEAR" in label: return "BEAR"
    return "MIXED"

def call_ai_with_fallback(prompt, models_rank, trader_name=None):
    preferred_models = [m["id"] if isinstance(m, dict) else str(m) for m in models_rank]
    return call_ai_json_with_fallback(prompt, models=preferred_models, name=trader_name or "AI Trader", log_func=log_event, category="trader", trader_name=trader_name)

def execute_trade_actions(trader_name, actions, current_cash, snapshots, model_id, market_features=None, use_shadow=False):
    # Внутренняя функция теперь использует Decimal и поддерживает тень
    with closing(get_db_connection()) as conn:
        try:
            review = review_actions(conn, trader_name, actions or [], snapshots, market_features or {}, settings=RiskSettings.from_env(), use_shadow=use_shadow)
            accepted = review.get("accepted", [])
            rejected = review.get("rejected", [])
            log_event(f"[{trader_name}] {'[SHADOW] ' if use_shadow else ''}Risk review: accepted={len(accepted)} rejected={len(rejected)}")
            
            if accepted:
                cur = conn.cursor()
                prefix = "shadow_" if use_shadow else ""
                for order in accepted:
                    cur.execute(f"""
                        INSERT INTO trading.{prefix}orders (trader_name, secid, order_type, quantity, target_price, status, model_id, reason)
                        VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s)
                    """, (trader_name, order["secid"], order["order_type"], order["quantity"], order["target_price"], model_id, order.get("reason", "")))
                conn.commit()
            return review
        except Exception as e:
            log_event(f"[{trader_name}] Risk processing failed: {e}")
            return None

def main():
    if len(sys.argv) < 2: return
    
    # Парсинг аргументов
    name = None
    use_shadow = "--shadow" in sys.argv
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            name = arg
            break
            
    if not name or name not in TRADERS_DATA: return
    
    with open(MODEL_RANK_FILE) as f: models = sorted(json.load(f)['models'], key=lambda x: x['priority'])
    
    with closing(get_db_connection()) as conn:
        market_context = load_market_context(conn)
        if not market_context: return
        stock_context = {secid: payload for secid, payload in market_context.items() if payload.get('engine') == 'stock'}
        snapshots = build_price_snapshot(stock_context)
        
        cur = conn.cursor()
        prefix = "shadow_" if use_shadow else ""
        cur.execute(f"SELECT cash_balance FROM trading.{prefix}portfolio WHERE trader_name = %s", (name,))
        row = cur.fetchone(); 
        if not row and use_shadow:
            # Авто-инициализация клона если его еще нет в тени
            cur.execute(f"INSERT INTO trading.shadow_portfolio (trader_name, cash_balance) VALUES (%s, %s)", (name, INITIAL_CAPITAL))
            conn.commit()
            cash = INITIAL_CAPITAL
        else:
            cash = _decimal(row[0]) if row else Decimal("0.0")
        
        cur.execute(f"SELECT secid, quantity, avg_entry_price FROM trading.{prefix}position WHERE trader_name = %s AND quantity > 0", (name,))
        positions = []
        for r in cur.fetchall():
            secid, qty, avg_p = r[0], int(r[1]), _decimal(r[2])
            curr_p = _decimal(snapshots.get(secid, {}).get("price", avg_p))
            pnl = ((curr_p / avg_p) - 1) * 100 if avg_p > 0 else Decimal("0")
            positions.append({"secid": secid, "qty": qty, "avg_price": avg_p, "curr_price": curr_p, "pnl_pct": round(float(pnl), 2)})
            
        cur.execute("SELECT learned_traits FROM trading.trader_config WHERE trader_name = %s", (name,)); traits = cur.fetchone()[0]
        cur.execute(f"SELECT action, secid, quantity, price, created_at FROM trading.{prefix}journal WHERE trader_name = %s ORDER BY created_at DESC LIMIT 3", (name,))
        recent_history = [f"{r[4].strftime('%H:%M')} {r[0]} {r[1]} x{r[2]} @{r[3]}" for r in cur.fetchall()]
        
        league_recent_trades = ""
        if name == "Meta_Oracle":
            cur.execute(f"SELECT trader_name, action, secid FROM trading.{prefix}journal WHERE created_at > now() - interval '1 hour' ORDER BY created_at DESC LIMIT 10")
            league_recent_trades = " | ".join([f"{r[0]} {r[1]} {r[2]}" for r in cur.fetchall()])
            league_ratings = load_weighted_consensus(conn)
        else: league_ratings = []

    prompt_market = compact_prompt_market_payload(build_trader_market_payload(stock_context, name))
    rag_context = build_trader_rag_context(trader_name=name, strategy=TRADERS_DATA[name]["strategy"], market_features=prompt_market, positions=positions, recent_history=recent_history, log_func=log_event)
    
    prompt = f"ROLE={name}; DNA={TRADERS_DATA[name]['strategy']}; traits={traits}; cash={float(cash):.2f}. POS={json.dumps(compact_positions_for_prompt(positions))}. MKT={json.dumps(prompt_market)}. RAG={rag_context}. Return ONLY JSON: actions[{{secid,action,target_price,reason}}]."
    
    decisions, used_model = call_ai_with_fallback(prompt, models, trader_name=name)
    if decisions:
        log_analytics_event(name, "ai_response", {"model": used_model, "decision": decisions, "is_shadow": use_shadow})
        review = execute_trade_actions(name, decisions.get("actions", []), cash, snapshots, used_model, market_features=prompt_market, use_shadow=use_shadow)
        if review:
            log_analytics_event(name, "risk_review", {"accepted": len(review.get("accepted", [])), "rejected": len(review.get("rejected", [])), "rejection_reasons": [r.get("reason") for r in review.get("rejected", [])], "state": review.get("state"), "is_shadow": use_shadow})
    else:
        reason = get_latest_ai_failure_reason(name)
        log_analytics_event(name, "ai_failed", {"reason": reason, "is_shadow": use_shadow})
        send_telegram(f"🔴 <b>{name} {'(SHADOW)' if use_shadow else ''}</b>: ИИ-решение не получено. {reason}")

if __name__ == "__main__": main()
