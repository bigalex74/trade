#!/usr/bin/env python3
import psycopg2, json, os, requests, sys, html, threading, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Настройка буферизации для логов
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

from market_research_context import build_price_snapshot, compact_context_payload, load_market_context
from gemini_cli_runner import call_ai_json_with_fallback
from hybrid_rag import build_trader_rag_context
from risk_engine import RiskSettings, review_actions
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
INITIAL_CAPITAL = 10000.0

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

    # Запуск отправки в отдельном потоке (fire-and-forget)
    threading.Thread(target=_send, daemon=True).start()

def log_analytics_event(trader_name, event_type, data):
    """Записывает структурированное событие для последующего анализа."""
    # Логи храним в подпапке analytics, по одному файлу на день
    analytics_dir = os.path.join(LOG_DIR, "analytics")
    os.makedirs(analytics_dir, exist_ok=True)
    filename = os.path.join(analytics_dir, f"events_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "trader": trader_name,
        "event": event_type,
        "data": data
    }
    try:
        with open(filename, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass

def format_money(val): return f"{float(val):,.2f}"
def format_pct(val): return f"{float(val):+.2f}%"
def format_trade_time(dt): return dt.strftime("%H:%M")

def get_trader_report(name, snapshots):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (name,))
    cash_balance = float(cur.fetchone()[0])
    cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
    positions = [{"secid": r[0], "quantity": r[1], "avg_price": float(r[2])} for r in cur.fetchall()]
    cur.execute("SELECT secid, action, quantity, price, created_at FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours' ORDER BY created_at DESC", (name,))
    trades_today = cur.fetchall()
    cur.close(); conn.close()

    positions_value = sum(p["quantity"] * snapshots.get(p["secid"], {"price": p["avg_price"]})["price"] for p in positions)
    equity = cash_balance + positions_value
    pnl_total = equity - INITIAL_CAPITAL
    pnl_total_pct = (pnl_total / INITIAL_CAPITAL) * 100
    buy_count = sum(1 for t in trades_today if str(t[1]).lower() in ["buy", "add"])
    sell_count = sum(1 for t in trades_today if str(t[1]).lower() in ["sell", "close", "reduce"])
    positions_preview = ", ".join(f"{item['secid']} x{item['quantity']}" for item in positions[:4])

    recent_trades = []
    for secid, action, quantity, price, created_at in trades_today[:3]:
        action_label = TRADE_VERB_LABELS.get(str(action).lower(), str(action).lower())
        recent_trades.append(f"{format_trade_time(created_at)} {action_label} {secid} x{quantity} по {format_money(price)}")

    return {
        "cash_balance": cash_balance, "positions_value": positions_value, "positions_count": len(positions),
        "positions_preview": positions_preview, "equity": equity, "pnl_total": pnl_total,
        "pnl_total_pct": pnl_total_pct, "trades_today_count": len(trades_today),
        "buy_count": buy_count, "sell_count": sell_count, "recent_trades": recent_trades,
    }

def build_trader_report_message(trader_name, report):
    lines = [
        f"👤 <b>{html.escape(trader_name)}</b>: краткий отчет",
        f"Капитал: {format_money(report['equity'])} ₽ ({format_pct(report['pnl_total_pct'])} к старту)",
        f"Кэш: {format_money(report['cash_balance'])} ₽ | Позиции: {format_money(report['positions_value'])} ₽ ({report['positions_count']})",
    ]
    if report["trades_today_count"]:
        lines.append(f"Сегодня: {report['trades_today_count']} сделок | купил {report['buy_count']} | продал {report['sell_count']}")
        if report["recent_trades"]:
            lines.append("Последние сделки:")
            lines.extend(f"• {trade}" for trade in report["recent_trades"])
    else: lines.append("Сегодня: новых сделок не было.")
    if report["positions_preview"]: lines.append(f"Портфель: {html.escape(report['positions_preview'])}")
    return "\n".join(lines)

def call_ai_with_fallback(prompt, models_rank, trader_name=None):
    preferred_models = [m["id"] if isinstance(m, dict) else str(m) for m in models_rank]
    return call_ai_json_with_fallback(
        prompt,
        models=preferred_models,
        name=trader_name or "AI Trader",
        log_func=log_event,
        include_ollama=False,
        category="trader",
        trader_name=trader_name,
    )


def get_latest_ai_failure_reason(trader_name):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT model_id, status, error_class, error, prompt_chars
            FROM trading.ai_call_log
            WHERE trader_name = %s OR call_name = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (trader_name, trader_name),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        row = None
    if not row:
        return "причина не определена, смотри лог трейдера"

    model_id, status, error_class, error, prompt_chars = row
    if status == "budget_blocked" and error_class == "prompt_too_large":
        return f"запрос превысил лимит ({prompt_chars} символов)"
    if status == "budget_blocked" and error_class == "hourly_limit":
        return "сработал часовой лимит ИИ-запросов"
    if status == "timeout":
        return f"модель {model_id} не ответила за отведенное время"
    if status == "model_skipped":
        return f"модель {model_id} временно на паузе после предыдущей ошибки"
    if status == "exhausted":
        return f"модель {model_id} вернула лимит или перегрузку"
    if error_class:
        return "техническая ошибка ИИ-вызова, подробности в логе трейдера"
    return "причина не определена, смотри лог трейдера"


def compact_positions_for_prompt(positions):
    return [
        {
            "s": item.get("secid"),
            "q": item.get("qty"),
            "avg": round(float(item.get("avg_price") or 0), 2),
            "pnl": round(float(item.get("pnl_pct") or 0), 2),
        }
        for item in (positions or [])
    ]


def compact_macro_for_prompt(payload):
    data = compact_context_payload(payload)
    if not isinstance(data, dict):
        return data
    return {
        key: data.get(key)
        for key in ("price", "day_change", "hour_change", "five_min_change")
        if data.get(key) is not None
    }


def compact_regime_label(label):
    value = str(label or "").lower()
    if "bear" in value:
        return "bear"
    if "bull" in value:
        return "bull"
    return "mixed"

# SECTOR MAPPING FOR CORRELATION PROTECTION
SECTOR_MAP = {
    "ROSN": "OIL", "LKOH": "OIL", "SNGSP": "OIL", "TATN": "OIL",
    "SBER": "FIN", "VTBR": "FIN", "TCSG": "FIN",
    "YNDX": "IT", "OZON": "IT", "ASTR": "IT",
    "GAZP": "GAS", "NVTK": "GAS",
    "GMKN": "METALS", "CHMF": "METALS", "NLMK": "METALS", "MAGN": "METALS",
    "ALRS": "DIAMONDS", "PLZL": "GOLD", "UGLD": "GOLD",
    "MGNT": "RETAIL", "FIVE": "RETAIL",
    "AFLT": "TRANSPORT",
    "MTSS": "TELECOM", "IRAO": "ENERGY", "FEES": "ENERGY",
}

def _legacy_execute_trade_actions(trader_name, actions, current_cash, snapshots, model_id):
    if not actions: return
    conn = get_db_connection(); cur = conn.cursor()
    
    # 1. Macro-Hedge (Защита от обвалов рынка и Market Breadth)
    macro_risk_modifier = 1.0
    usd_data = snapshots.get("USD000UTSTOM", {})
    if usd_data:
        usd_change = usd_data.get("change_pct", 0)
        if usd_change is not None and usd_change > 1.5:
            log_event(f"[{trader_name}] Macro Alert: USD is up {usd_change:.2f}%. Reducing risk per trade.")
            macro_risk_modifier *= 0.5
            
    # Расчет Market Breadth (% акций выше SMA 50)
    total_stocks = 0; above_sma50 = 0
    for sec, data in snapshots.items():
        if sec in ["USD000UTSTOM", "BRENT", "GLDRUB_TOM", "NGH6"]: continue
        inds = data.get("indicators", {})
        if not inds: continue
        sma50 = inds.get("SMA_50")
        price = data.get("price")
        if sma50 and price:
            total_stocks += 1
            if price > sma50: above_sma50 += 1
            
    market_breadth = (above_sma50 / total_stocks) * 100 if total_stocks else 50.0
    if market_breadth < 30.0:
        log_event(f"[{trader_name}] Market Breadth Alert: Only {market_breadth:.1f}% stocks above SMA50. Risk reduced.")
        macro_risk_modifier *= 0.5

    cur.execute("SELECT SUM(quantity * avg_entry_price) FROM trading.position WHERE trader_name = %s", (trader_name,))
    pos_val = float(cur.fetchone()[0] or 0); equity = current_cash + pos_val
    limit_per_asset = equity * 0.15; risk_per_trade = equity * 0.01 * macro_risk_modifier
    if trader_name == "Meta_Oracle":
        limit_per_asset = equity * 0.30
        risk_per_trade = equity * 0.03 * macro_risk_modifier

    limit_per_sector = equity * 0.25 # Не более 25% в одном секторе

    for act in actions:
        secid = act.get("secid"); action_type = str(act.get("action")).lower(); reason = act.get("reason", "No reason")
        ticker_data = snapshots.get(secid, {}); price = ticker_data.get("price"); indicators = ticker_data.get("indicators", {})
        if not price: continue

        cur.execute("SELECT quantity, avg_entry_price, created_at FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
        pos_row = cur.fetchone()
        if pos_row and pos_row[0] > 0:
            created_at = pos_row[2]
            # Защита 1: CK_STOP
            ck_long = indicators.get("CK_STOP_LONG")
            if ck_long and price < ck_long:
                action_type = "sell"; reason = f"STOP-LOSS: Price {price} < CK_STOP {ck_long:.2f}"
            # Защита 2: Time-based Exit (4 часа без прибыли)
            elif created_at:
                time_held = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
                if time_held > 4.0 and price < float(pos_row[1]):
                    action_type = "sell"; reason = f"TIME-EXIT: Held {time_held:.1f}h without profit"

        if action_type in ["buy", "add", "short"]:
            # Проверка сентимента (News Oracle)
            sentiment_score = ticker_data.get("sentiment", {}).get("score", 0)
            if action_type in ["buy", "add"] and sentiment_score < -0.5:
                log_event(f"[{trader_name}] Cancel BUY {secid}: Sentiment Oracle blocks due to score {sentiment_score:.2f}")
                continue

            atr = indicators.get("ATRr_14", price * 0.02)
            qty = max(1, int(risk_per_trade / atr)) if atr > 0 else 1
            cost = price * qty
            
            # Для лонга нужны деньги, для шорта нужно обеспечение (margin)
            if action_type != "short" and current_cash < cost: 
                qty = int(current_cash / price); cost = price * qty
            if qty <= 0: continue
            
            cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s", (trader_name,))
            all_positions = cur.fetchall()
            curr_qty, curr_avg = next(((q, float(a)) for s, q, a in all_positions if s == secid), (0, 0.0))
            
            if action_type == "short":
                # Для шорта мы продаем то, чего нет (или увеличиваем шорт)
                qty = -qty
                income = price * abs(qty)
                # Проверка лимита на шорт (чтобы не уйти в маржин-колл)
                if abs(curr_qty + qty) * price > limit_per_asset: continue
                new_qty = curr_qty + qty
                # Для шорта средняя цена считается так же (по модулю)
                new_avg = ((abs(curr_qty) * curr_avg) + income) / abs(new_qty) if new_qty != 0 else 0
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (income, trader_name))
                current_cash += income
                act_str = "SHORT"
            else:
                if (curr_qty * curr_avg) + cost > limit_per_asset: continue
                # Проверка по секторам (только для лонгов)
                target_sector = SECTOR_MAP.get(secid, "OTHER")
                sector_exposure = sum(q * float(a) for s, q, a in all_positions if q > 0 and SECTOR_MAP.get(s, "OTHER") == target_sector)
                if sector_exposure + cost > limit_per_sector: continue
                new_qty = curr_qty + qty
                new_avg = ((curr_qty * curr_avg) + cost) / new_qty if new_qty != 0 else 0
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (cost, trader_name))
                current_cash -= cost
                act_str = "BUY"
            
            cur.execute("INSERT INTO trading.position (trader_name, secid, quantity, avg_entry_price, updated_at) VALUES (%s,%s,%s,%s,NOW()) ON CONFLICT (trader_name, secid) DO UPDATE SET quantity=EXCLUDED.quantity, avg_entry_price=EXCLUDED.avg_entry_price, updated_at=NOW()", (trader_name, secid, new_qty, new_avg))
            cur.execute("INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, indicators_snapshot, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())", (trader_name, secid, act_str, abs(qty), price, reason, model_id, json.dumps(indicators)))
            log_event(f"[{trader_name}] EXECUTED {act_str}: {secid} x{abs(qty)} @{price}")

        elif action_type in ["sell", "close", "reduce", "cover"]:
            cur.execute("SELECT quantity FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
            row = cur.fetchone()
            if not row: continue
            curr_qty = row[0]
            if curr_qty == 0: continue
            
            if action_type == "cover" and curr_qty < 0:
                # Откуп шорта
                qty_to_cover = abs(curr_qty) if action_type == "cover" else max(1, abs(curr_qty) // 2)
                cost = price * qty_to_cover
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (cost, trader_name))
                current_cash -= cost
                if curr_qty + qty_to_cover >= 0:
                    cur.execute("DELETE FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
                else:
                    cur.execute("UPDATE trading.position SET quantity = quantity + %s WHERE trader_name = %s AND secid = %s", (qty_to_cover, trader_name, secid))
                cur.execute("INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, indicators_snapshot, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())", (trader_name, secid, "COVER", qty_to_cover, price, reason, model_id, json.dumps(indicators)))
                log_event(f"[{trader_name}] EXECUTED COVER: {secid} x{qty_to_cover} @{price}")
                
            elif curr_qty > 0 and action_type in ["sell", "close", "reduce"]:
                # Закрытие лонга
                qty_to_sell = curr_qty if action_type in ["sell", "close"] else max(1, curr_qty // 2)
                income = price * qty_to_sell
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (income, trader_name))
                current_cash += income
                if curr_qty - qty_to_sell <= 0:
                    cur.execute("DELETE FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
                else:
                    cur.execute("UPDATE trading.position SET quantity = quantity - %s WHERE trader_name = %s AND secid = %s", (qty_to_sell, trader_name, secid))
                cur.execute("INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, indicators_snapshot, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())", (trader_name, secid, "SELL", qty_to_sell, price, reason, model_id, json.dumps(indicators)))
                log_event(f"[{trader_name}] EXECUTED SELL: {secid} x{qty_to_sell} @{price}")

        elif action_type in ["limit_buy", "limit_sell", "stop_loss"]:
            # ОТЛОЖЕННЫЕ ОРДЕРА
            target_price = act.get("target_price")
            if not target_price:
                log_event(f"[{trader_name}] Target price missing for {action_type} {secid}")
                continue
            atr = indicators.get("ATRr_14", price * 0.02)
            qty = max(1, int(risk_per_trade / atr)) if atr > 0 else 1
            cur.execute("""
                INSERT INTO trading.orders (trader_name, secid, order_type, quantity, target_price, status, model_id, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s, NOW())
            """, (trader_name, secid, action_type, qty, target_price, model_id, reason))
            log_event(f"[{trader_name}] PLACED ORDER: {action_type} {secid} x{qty} @{target_price}")

    conn.commit(); cur.close(); conn.close()

def _env_enabled(name):
    return os.getenv(name, "0").lower() in {"1", "true", "yes", "on"}

def execute_trade_actions(trader_name, actions, current_cash, snapshots, model_id, market_features=None):
    conn = get_db_connection()
    try:
        review = review_actions(
            conn,
            trader_name,
            actions or [],
            snapshots,
            market_features or {},
            settings=RiskSettings.from_env(),
        )
        accepted = review.get("accepted", [])
        rejected = review.get("rejected", [])
        log_event(f"[{trader_name}] Risk review: accepted={len(accepted)} rejected={len(rejected)} state={review.get('state')}")
        for item in rejected[:5]:
            action = item.get("action") or {}
            log_event(f"[{trader_name}] Risk rejected {action.get('action')} {action.get('secid')}: {item.get('reason')}")

        if _env_enabled("AI_TRADER_DRY_RUN"):
            conn.rollback()
            log_event(f"[{trader_name}] DRY RUN: orders were not written.")
            return review

        cur = conn.cursor()
        for order in accepted:
            cur.execute(
                """
                INSERT INTO trading.orders
                    (trader_name, secid, order_type, quantity, target_price, status, model_id, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s, NOW())
                """,
                (
                    trader_name,
                    order["secid"],
                    order["order_type"],
                    order["quantity"],
                    order["target_price"],
                    model_id,
                    order.get("reason", ""),
                ),
            )
            log_event(
                f"[{trader_name}] PLACED ORDER: {order['order_type']} "
                f"{order['secid']} x{order['quantity']} @{order['target_price']}"
            )
        cur.close()
        conn.commit()
        return review
    except Exception as e:
        conn.rollback()
        log_event(f"[{trader_name}] Risk/order processing failed: {e}")
        return None
    finally:
        conn.close()

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TRADERS_DATA: return
    name = sys.argv[1]
    with open(MODEL_RANK_FILE) as f: models = sorted(json.load(f)['models'], key=lambda x: x['priority'])
    market_context = load_market_context()
    if not market_context: return
    stock_context = {secid: payload for secid, payload in market_context.items() if payload.get('engine') == 'stock'}
    relevant_ids = list(stock_context.keys())
    snapshots = build_price_snapshot(stock_context)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (name,)); cash = float(cur.fetchone()[0])
    cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
    positions = []
    for r in cur.fetchall():
        secid, qty, avg_price = r[0], r[1], float(r[2]); curr_price = snapshots.get(secid, {}).get("price")
        pnl_pct = ((curr_price / avg_price) - 1) * 100 if curr_price and avg_price else 0.0
        positions.append({"secid": secid, "qty": qty, "avg_price": avg_price, "curr_price": curr_price, "pnl_pct": round(pnl_pct, 2)})
    cur.execute("SELECT action, secid, quantity, price, created_at FROM trading.journal WHERE trader_name = %s ORDER BY created_at DESC LIMIT 3", (name,))
    recent_history = [f"{r[4].strftime('%H:%M')} {r[0]} {r[1]} x{r[2]} @{r[3]}" for r in cur.fetchall()]
    cur.execute("SELECT learned_traits FROM trading.trader_config WHERE trader_name = %s", (name,)); traits = cur.fetchone()[0]

    # META-ORACLE: Получение списка сделок всей Лиги за последний час
    league_recent_trades = ""
    if name == "Meta_Oracle":
        oracle_trades_limit = int(os.getenv("AI_META_ORACLE_LEAGUE_TRADES_LIMIT", "12"))
        cur.execute(
            "SELECT trader_name, action, secid, created_at FROM trading.journal "
            "WHERE created_at > now() - interval '1 hour' ORDER BY created_at DESC LIMIT %s",
            (oracle_trades_limit,),
        )
        league_recent_trades = " | ".join([f"[{r[3].strftime('%H:%M')}] {r[0]} {r[1]} {r[2]}" for r in cur.fetchall()])

    filtered_market = build_trader_market_payload(stock_context, name)
    cur.execute("SELECT secid, score, summary FROM analytics.market_sentiment")
    sentiment_data = {r[0]: {"score": float(r[1]), "summary": r[2]} for r in cur.fetchall()}

    total_stocks = 0; above_sma50 = 0
    for secid, data in sentiment_data.items():
        if secid in filtered_market:
            filtered_market[secid]["sent_score"] = data["score"]
            if data.get("summary"):
                filtered_market[secid]["sent"] = str(data["summary"])[:160]
        if secid in snapshots:
            snapshots[secid]["sentiment"] = data

    # Расчет режима рынка
    for sec, data in snapshots.items():
        if sec in ['USD000UTSTOM', 'BRENT', 'GLDRUB_TOM', 'NGH6']: continue
        inds = data.get("indicators", {})
        price = data.get("price")
        if inds and price and inds.get("SMA_50"):
            total_stocks += 1
            if price > inds.get("SMA_50"): above_sma50 += 1

    market_breadth = (above_sma50 / total_stocks) * 100 if total_stocks else 50.0
    if market_breadth < 30.0: market_regime = "BEAR MARKET (Favorable for Shorting)"
    elif market_breadth > 70.0: market_regime = "BULL MARKET (Favorable for Longs)"
    else: market_regime = "SIDEWAYS / MIXED MARKET"

    league_ratings = []
    if name == "Meta_Oracle":
        league_ratings = load_weighted_consensus(conn, limit=int(os.getenv("AI_META_ORACLE_RATINGS_LIMIT", "6")))

    cur.close(); conn.close()
    prompt_market = compact_prompt_market_payload(filtered_market)
    log_event(f"[{name}] Market features: {payload_stats(filtered_market)}")
    log_event(f"[{name}] Prompt market features: {payload_stats(prompt_market)}")

    EXPERT_GUIDES = {

        "VSA_Victor": "VSA: volume/spread/climax near levels.",
        "Chaos_Bill": "Chaos: Alligator + fractals; buy only above teeth with fresh up fractal.",
        "Elliott_Alex": "Elliott: waves; RSI/MACD exhaustion or trend start.",
        "Contrarian_Ricardo": "Contrarian: BB/RSI extremes; fade stretched moves.",
        "Quant_Diana": "Quant: ADX/TSI confirm; avoid CHOP>61.",
        "PriceAction_Nikita": "Price action: levels, range/body, Donchian/SAR direction.",
        "Passive_Palych": "Passive: long trend, liquidity, ATR sizing.",
        "Scalper_Kesha": "Scalp: 5m flow, RSI extremes, quick exits.",
        "Value_Monya": "Value: long trend and value bias, ignore noise.",
        "Index_Tracker": "Index: mirror broad MOEX and macro correlation.",
        "Meta_Oracle": "Oracle: act only on strong weighted league consensus."
    }
    rag_context = build_trader_rag_context(
        trader_name=name,
        strategy=TRADERS_DATA[name]["strategy"],
        market_features=prompt_market,
        positions=positions,
        recent_history=recent_history,
        market_regime=market_regime,
        log_func=log_event,
    )
    def render_prompt(market_payload, rag_block, history_items, oracle_trades, oracle_ratings):
        prompt_parts = [
            f"ROLE={name}; DNA={TRADERS_DATA[name]['strategy']}; traits={traits}; cash={round(cash, 2)}.",
            f"REGIME={compact_regime_label(market_regime)}; breadth={market_breadth:.1f}.",
            f"POS={json.dumps(compact_positions_for_prompt(positions), ensure_ascii=False, separators=(',', ':'))}.",
            f"HIST={';'.join(history_items)}." if history_items else "",
            f"MACRO={json.dumps(compact_macro_for_prompt(market_context.get('USD000UTSTOM')), ensure_ascii=False, separators=(',', ':'))}.",
            f"MKT={json.dumps(market_payload, ensure_ascii=False, separators=(',', ':'))}.",
            f"RULE={EXPERT_GUIDES.get(name, 'Use signals, risk, liquidity.')}",
            f"RAG={rag_block}" if rag_block else "",
            f"LEAGUE={oracle_trades}" if name == "Meta_Oracle" and oracle_trades else "",
            f"RATINGS={oracle_ratings}" if name == "Meta_Oracle" and oracle_ratings else "",
            "KEYS: t up/down/range/panic/mix; m5/h1/d1 %; v5/vh volume ratio; vw VWAP%; atr risk%; liq H/M/L; sent sentiment.",
            "ACTIONS: buy/sell/limit_buy/limit_sell/stop_loss/short/cover; target_price only for limit/stop.",
            "Return ONLY JSON: summary, market_bias, confidence, actions[{secid,action,target_price,reason}], risk_notes."
        ]
        return " ".join(part for part in prompt_parts if part)

    prompt_history = recent_history[: int(os.getenv("AI_TRADER_HISTORY_LIMIT", "2"))]
    prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
    prompt_limit = int(os.getenv("AI_PROMPT_MAX_CHARS_TRADER", os.getenv("AI_PROMPT_MAX_CHARS", "8000")))
    prompt_target = min(prompt_limit, int(os.getenv("AI_PROMPT_TARGET_CHARS_TRADER", "5200")))
    prompt_margin = int(os.getenv("AI_RAG_PROMPT_MARGIN_CHARS", "120"))
    if rag_context and len(prompt) > prompt_target:
        overflow = len(prompt) - prompt_target + prompt_margin
        if len(rag_context) > overflow + int(os.getenv("AI_RAG_MIN_CHARS", "240")):
            keep_chars = max(0, len(rag_context) - overflow - 1)
            rag_context = rag_context[:keep_chars].rstrip() + "…"
            log_event(f"[{name}] Hybrid RAG trimmed to fit prompt budget: chars={len(rag_context)}")
        else:
            rag_context = ""
            log_event(f"[{name}] Hybrid RAG skipped: prompt target too tight ({len(prompt)}>{prompt_target})")
        prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
    if len(prompt) > prompt_target and name == "Meta_Oracle" and len(league_ratings) > 3:
        original_ratings = len(league_ratings)
        league_ratings = league_ratings[:3]
        prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
        log_event(f"[{name}] League ratings trimmed for prompt budget: {original_ratings}->3")
    min_symbols = int(os.getenv("AI_TRADER_MIN_SYMBOLS", "5"))
    original_symbols = len(prompt_market)
    while len(prompt) > prompt_target and len(prompt_market) > min_symbols:
        prompt_market = dict(list(prompt_market.items())[:-1])
        prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
    if len(prompt_market) != original_symbols:
        log_event(f"[{name}] Prompt market features trimmed: {original_symbols}->{len(prompt_market)}")
    if len(prompt) > prompt_target and prompt_history:
        prompt_history = prompt_history[:1]
        prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
        log_event(f"[{name}] Recent history trimmed for prompt budget.")
    if len(prompt) > prompt_target and rag_context:
        rag_context = ""
        prompt = render_prompt(prompt_market, rag_context, prompt_history, league_recent_trades, league_ratings)
        log_event(f"[{name}] Hybrid RAG removed after final prompt budget check.")
    log_event(f"[{name}] Prompt chars: {len(prompt)} target={prompt_target} limit={prompt_limit}")
    if len(prompt) > prompt_limit:
        log_event(f"[{name}] Prompt remains above budget after trimming: {len(prompt)}>{prompt_limit}.")
    decisions, used_model = call_ai_with_fallback(prompt, models, trader_name=name)
    if decisions is not None:
        log_analytics_event(name, "ai_response", {
            "model": used_model,
            "actions_count": len(decisions.get("actions", [])),
            "confidence": decisions.get("confidence"),
            "decision": decisions
        })
        review = execute_trade_actions(name, decisions.get("actions", []), cash, snapshots, used_model, market_features=filtered_market)
        if review:
            log_analytics_event(name, "risk_review", {
                "accepted": len(review.get("accepted", [])),
                "rejected": len(review.get("rejected", [])),
                "rejection_reasons": [r.get("reason") for r in review.get("rejected", [])],
                "state": review.get("state")
            })
    else:
        log_analytics_event(name, "ai_failed", {"prompt_len": len(prompt)})
        reason = get_latest_ai_failure_reason(name)
        log_event(f"[{name}] AI decision unavailable: {reason}.")
        send_telegram(f"🔴 <b>{name}</b>: ИИ-решение не получено. Причина: {html.escape(reason)}.")

if __name__ == "__main__": main()
