#!/usr/bin/env python3
import psycopg2, json, subprocess, os, requests, sys, html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Настройка буферизации для логов
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

from market_research_context import build_price_snapshot, compact_context_payload, load_market_context

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL_RANK_FILE = "/home/user/ai_model_rank.json"
LOG_FILE = "/home/user/logs/ai_trader.log"
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

# LOAD BALANCING CONFIG
TRADER_MODELS = {
    "VSA_Victor": ["gemini-1.5-pro", "gemini-1.5-flash"],
    "Chaos_Bill": ["gemini-1.5-pro", "gemini-1.5-flash"],
    "Elliott_Alex": ["gemini-1.5-pro", "gemini-1.5-flash"],
    "Quant_Diana": ["gemini-1.5-flash", "gemini-1.5-pro"],
    "PriceAction_Nikita": ["gemini-1.5-flash", "gemini-1.5-pro"],
    "Contrarian_Ricardo": ["gemini-1.5-flash", "gemini-1.5-pro"],
    "Passive_Palych": ["ollama/llama3.2", "gemini-1.5-flash"],
    "Value_Monya": ["ollama/llama3.2", "gemini-1.5-flash"],
    "Index_Tracker": ["ollama/llama3.2", "gemini-1.5-flash"],
    "Scalper_Kesha": ["gemini-1.5-flash", "ollama/llama3.2"],
    "Meta_Oracle": ["gemini-1.5-pro", "gemini-1.5-flash"]
}

TRADE_VERB_LABELS = {
    "buy": "купил",
    "add": "добавил",
    "sell": "продал",
    "close": "закрыл",
    "reduce": "сократил",
}

def log_event(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
        requests.post(url, json=payload, proxies=proxies, timeout=10)
    except: pass

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

def notify_model_switch(current_model, next_model, reason, trader_name=None):
    trader_label = trader_name or "AI Trader"
    next_label = next_model or "нет следующей модели"
    log_event(f"[{trader_label}] Переключение модели: {current_model} -> {next_label}. Причина: {reason}")
    send_telegram(f"⚠️ <b>{html.escape(trader_label)}</b>: переключение модели\n<code>{html.escape(current_model)}</code> → <code>{html.escape(next_label)}</code>\nПричина: {html.escape(reason)}")

def is_capacity_error(stdout, stderr):
    output = (stdout or "") + (stderr or "")
    return any(x in output.lower() for x in ["capacity", "overloaded", "quota", "exhausted", "429"])

def call_ai_with_fallback(prompt, models_rank, trader_name=None):
    preferred_models = TRADER_MODELS.get(trader_name, [m['id'] for m in models_rank])
    for index, model_id in enumerate(preferred_models):
        next_model = preferred_models[index + 1] if index + 1 < len(preferred_models) else None
        
        if model_id.startswith("ollama/"):
            ollama_name = model_id.replace("ollama/", "")
            try:
                res = subprocess.run(["ollama", "run", ollama_name, prompt], capture_output=True, text=True, timeout=180)
                if res.returncode == 0 and "{" in res.stdout:
                    json_str = res.stdout[res.stdout.find("{"):res.stdout.rfind("}")+1]
                    return json.loads(json_str), model_id
                else: continue
            except: continue

        cmd = ["gemini", "-p", prompt, "--model", model_id, "--output-format", "json", "--approval-mode", "yolo"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if is_capacity_error(res.stdout, res.stderr):
                notify_model_switch(model_id, next_model, "исчерпана квота", trader_name=trader_name); continue
            if res.returncode != 0: continue
            raw_out = res.stdout
            if "```json" in raw_out: raw_out = raw_out.split("```json")[1].split("```")[0]
            try:
                data = json.loads(raw_out)
                resp_text = data.get("response", "")
                if isinstance(resp_text, str) and resp_text.strip().startswith("{"): return json.loads(resp_text), model_id
                return data, model_id
            except: continue
        except: continue
    return None, None

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

def execute_trade_actions(trader_name, actions, current_cash, snapshots, model_id):
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
        cur.execute("SELECT trader_name, action, secid, created_at FROM trading.journal WHERE created_at > now() - interval '1 hour' ORDER BY created_at DESC LIMIT 20")
        league_recent_trades = " | ".join([f"[{r[3].strftime('%H:%M')}] {r[0]} {r[1]} {r[2]}" for r in cur.fetchall()])

    cur.close(); conn.close()

    filtered_market = {ticker: compact_context_payload(stock_context[ticker]) for ticker in sorted(relevant_ids) if ticker in stock_context}
    EXPERT_GUIDES = {
        "VSA_Victor": "Focus on volume/price spread. Check if price is at Donchian Channel extremes with high volume (Climax).",
        "Chaos_Bill": "Priority: Williams Alligator (AL_JAW/TEETH/LIPS) and Fractals. Buy ONLY if price is above the teeth and a fresh fractal_up appears.",
        "Elliott_Alex": "Identify wave structures. Use RSI and MACD to find momentum exhaustion (Wave 5) or trend start.",
        "Contrarian_Ricardo": "Look for Bollinger Bands (BB_UP/BB_LOW) touches and high RSI (>75) or low RSI (<25) for reversals.",
        "Quant_Diana": "Analyze ADX for trend strength and TSI (True Strength Index) for signal confirmation. Avoid trades if CHOP > 61.",
        "PriceAction_Nikita": "Focus on Donchian Channels and SMA/EMA/WMA crossovers. Check Parabolic SAR (PSAR) for trend direction.",
        "Passive_Palych": "Analyze long-term EMA/SMA 200 and Dividend consistency. Use ATR for volatility-adjusted position sizing.",
        "Scalper_Kesha": "High-frequency focus. Use 5m windows, Parabolic SAR, and RSI extremes. Exit quickly if CK_STOP is hit.",
        "Value_Monya": "Fundamental value vs current price. Use long-term indicators (Yearly window) and SMA 200.",
        "Index_Tracker": "Mirror market moves. Focus on Macro indicators (USD, Gold, Oil) and their correlation with stocks.",
        "Meta_Oracle": "Collective Mind. You analyze the recent trades of the other 10 AI agents (LEAGUE TRADES). You buy ONLY when multiple independent algorithms buy the same asset. You use 3x position sizing."
    }
    prompt_parts = [
        f"Act as {name}. DNA: {TRADERS_DATA[name]['strategy']}. Traits: {traits}. Cash: {cash}.",
        f"Portfolio (with PnL): {json.dumps(positions)}.", f"Recent History: {'; '.join(recent_history)}.",
        f"Macro: {json.dumps(compact_context_payload(market_context.get('USD000UTSTOM')))}.",
        f"MARKET DATA: {json.dumps(filtered_market)}.",
        f"STRATEGIC GUIDELINE: {EXPERT_GUIDES.get(name, 'Use all indicators to maximize profit.')}",
        f"LEAGUE TRADES (For Oracle): {league_recent_trades}" if name == "Meta_Oracle" else "",
        "TECHNICAL MANUAL: - Alligator: Jaw(Blue), Teeth(Red), Lips(Green). Open mouth = trend. - CK_STOP: Chande Kroll Stop for exits. PSAR: Parabolic SAR for trend. - TSI: True Strength Index. RVI: Relative Vigor Index. CHOP: >61 means sideways market.",
        "ORDER TYPES: You can use 'buy', 'sell' (market execution). You can also use 'limit_buy', 'limit_sell', 'stop_loss' (must provide 'target_price'). You can use 'short' to short-sell, and 'cover' to close a short.",
        f"1. Query 'lightrag-algo' for '{TRADERS_DATA[name]['query']}'. 2. Respond ONLY raw JSON object with keys: summary, market_bias, confidence, actions (array with secid, action, target_price (optional), reason), risk_notes."
    ]
    prompt = " ".join(prompt_parts)
    decisions, used_model = call_ai_with_fallback(prompt, models, trader_name=name)
    if decisions is not None:
        execute_trade_actions(name, decisions.get("actions", []), cash, snapshots, used_model)
    else: send_telegram(f"🔴 <b>{name}</b>: Ошибка! Все AI модели недоступны.")

if __name__ == "__main__": main()
