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
MSK_TZ = ZoneInfo("Europe/Moscow")
TRADERS_DATA = {
    "VSA_Victor": {"strategy": "VSA Specialist.", "query": "VSA"}, "Chaos_Bill": {"strategy": "Chaos Theory.", "query": "Билл Вильямс"},
    "Elliott_Alex": {"strategy": "Elliott Waves.", "query": "Волны Эллиотта"}, "Contrarian_Ricardo": {"strategy": "Mean Reversion.", "query": "Контртренд"},
    "Quant_Diana": {"strategy": "Statistical.", "query": "Квант"}, "PriceAction_Nikita": {"strategy": "Price Action.", "query": "Прайс Экшен"},
    "Passive_Palych": {"strategy": "Dividends.", "query": "Дивиденды"}, "Scalper_Kesha": {"strategy": "Aggressive Scalper.", "query": "Скальпинг"},
    "Value_Monya": {"strategy": "Value Finder.", "query": "Фундаментал"}, "Index_Tracker": {"strategy": "Index Tracker.", "query": "Индекс"}
}

CAPACITY_ERROR_MARKERS = (
    "QUOTA_EXHAUSTED",
    "RESOURCE_EXHAUSTED",
    "exhausted your capacity on this model",
    "quota will reset after",
)

MARKET_BIAS_LABELS = {
    "bullish": "бычий сценарий",
    "bearish": "медвежий сценарий",
    "neutral": "нейтрально",
    "sideways": "боковик",
    "mixed": "смешанная картина",
}

ACTION_LABELS = {
    "buy": "покупка",
    "add": "добор",
    "accumulate": "накапливать",
    "sell": "продажа",
    "reduce": "сократить",
    "trim": "сократить",
    "hold": "держать",
    "watch": "наблюдать",
    "wait": "ждать",
    "skip": "пропустить",
    "close": "закрыть",
}

TRADE_VERB_LABELS = {
    "buy": "купил",
    "sell": "продал",
}

def send_telegram(message):
    global TELEGRAM_TOKEN
    if not TELEGRAM_TOKEN and os.path.exists("/home/user/.env"):
        with open("/home/user/.env") as f:
            for line in f:
                if "TELEGRAM_BOT_TOKEN=" in line: TELEGRAM_TOKEN = line.split("=")[1].strip()
    if not TELEGRAM_TOKEN: return
    proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, proxies=proxies, timeout=15)
    except Exception as e: print(f"TG Error: {e}")

def log_event(message):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def is_capacity_error(stdout_text, stderr_text):
    text = " ".join(filter(None, [stdout_text, stderr_text])).lower()
    return any(marker.lower() in text for marker in CAPACITY_ERROR_MARKERS)

def shorten_error(text, limit=240):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."

def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def humanize_value(value, mapping):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return mapping.get(text.lower(), text)

def normalize_actions(decisions):
    if isinstance(decisions, dict):
        for key in ("actions", "trades", "ideas", "recommendations", "decisions", "signals"):
            if key in decisions:
                return as_list(decisions[key])
    if isinstance(decisions, list):
        return decisions
    return []

def stringify_action(action):
    if isinstance(action, str):
        return action.strip()
    if not isinstance(action, dict):
        return shorten_error(json.dumps(action, ensure_ascii=False), 160)

    ticker = action.get("ticker") or action.get("secid") or action.get("symbol") or action.get("asset")
    action_name = action.get("action") or action.get("decision") or action.get("signal") or action.get("side")
    reason = action.get("reason") or action.get("thesis") or action.get("comment") or action.get("rationale")
    confidence = action.get("confidence") or action.get("priority") or action.get("conviction")

    parts = []
    action_label = humanize_value(action_name, ACTION_LABELS)

    if ticker and action_label:
        parts.append(f"{ticker}: {action_label}")
    elif ticker:
        parts.append(str(ticker))
    elif action_label:
        parts.append(str(action_label))

    if reason:
        parts.append(str(reason))
    if confidence:
        parts.append(f"уверенность: {confidence}")

    if parts:
        return " — ".join(parts)
    return shorten_error(json.dumps(action, ensure_ascii=False), 160)

def build_human_summary(decisions):
    if decisions is None:
        return None

    if isinstance(decisions, dict):
        summary = (
            decisions.get("summary")
            or decisions.get("brief")
            or decisions.get("thesis")
            or decisions.get("overview")
            or decisions.get("market_summary")
        )
        market_bias = (
            decisions.get("market_bias")
            or decisions.get("market_view")
            or decisions.get("bias")
            or decisions.get("stance")
            or decisions.get("regime")
        )
        confidence = decisions.get("confidence")
        actions = normalize_actions(decisions)
        risk_notes = as_list(
            decisions.get("risk_notes")
            or decisions.get("risks")
            or decisions.get("caution")
            or decisions.get("notes")
        )
    elif isinstance(decisions, list):
        summary = None
        market_bias = None
        confidence = None
        actions = decisions
        risk_notes = []
    else:
        summary = str(decisions)
        market_bias = None
        confidence = None
        actions = []
        risk_notes = []

    lines = []
    if summary:
        lines.append(f"Резюме: {summary}")
    if market_bias:
        bias_line = f"Рынок: {humanize_value(market_bias, MARKET_BIAS_LABELS)}"
        if confidence:
            bias_line += f" | уверенность: {confidence}"
        lines.append(bias_line)
    elif confidence:
        lines.append(f"Уверенность: {confidence}")

    action_lines = [stringify_action(action) for action in actions[:5] if stringify_action(action)]
    if action_lines:
        lines.append("Действия:")
        lines.extend([f"• {line}" for line in action_lines])
    elif not summary:
        lines.append("Явных торговых действий не предложено.")

    risk_lines = [str(note).strip() for note in risk_notes[:3] if str(note).strip()]
    if risk_lines:
        lines.append("Риски:")
        lines.extend([f"• {note}" for note in risk_lines])

    return "\n".join(lines)

def format_money(value):
    return f"{float(value):,.2f}".replace(",", " ")

def format_pct(value):
    return f"{float(value):+.2f}%"

def format_trade_time(value):
    if not value:
        return "--:--"
    return value.astimezone(MSK_TZ).strftime("%H:%M")

def get_trader_report(trader_name, snapshots):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s",
        (trader_name,),
    )
    row = cur.fetchone()
    cash_balance = float(row[0]) if row else 0.0

    cur.execute(
        """
        SELECT secid, quantity, avg_entry_price
        FROM trading.position
        WHERE trader_name = %s AND quantity > 0
        ORDER BY quantity DESC, secid
        """,
        (trader_name,),
    )
    positions = []
    positions_value = 0.0
    for secid, quantity, avg_entry_price in cur.fetchall():
        market_price = float(snapshots.get(secid, {}).get("price", avg_entry_price))
        market_value = quantity * market_price
        positions_value += market_value
        positions.append(
            {
                "secid": secid,
                "quantity": quantity,
                "market_value": market_value,
            }
        )

    start_of_day_msk = datetime.now(MSK_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_msk.astimezone(timezone.utc)
    cur.execute(
        """
        SELECT secid, action, quantity, price, created_at
        FROM trading.journal
        WHERE trader_name = %s AND created_at >= %s AND quantity > 0
        ORDER BY created_at DESC, id DESC
        """,
        (trader_name, start_of_day_utc),
    )
    trades_today = cur.fetchall()

    cur.close()
    conn.close()

    buy_count = sum(1 for _, action, *_ in trades_today if str(action).upper() == "BUY")
    sell_count = sum(1 for _, action, *_ in trades_today if str(action).upper() == "SELL")
    equity = cash_balance + positions_value
    pnl_total = equity - INITIAL_CAPITAL
    pnl_total_pct = (pnl_total / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL else 0.0

    positions_preview = ", ".join(
        f"{item['secid']} x{item['quantity']}" for item in positions[:4]
    )

    recent_trades = []
    for secid, action, quantity, price, created_at in trades_today[:3]:
        action_label = TRADE_VERB_LABELS.get(str(action).lower(), str(action).lower())
        recent_trades.append(
            f"{format_trade_time(created_at)} {action_label} {secid} x{quantity} по {format_money(price)}"
        )

    return {
        "cash_balance": cash_balance,
        "positions_value": positions_value,
        "positions_count": len(positions),
        "positions_preview": positions_preview,
        "equity": equity,
        "pnl_total": pnl_total,
        "pnl_total_pct": pnl_total_pct,
        "trades_today_count": len(trades_today),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "recent_trades": recent_trades,
    }

def build_trader_report_message(trader_name, report):
    lines = [
        f"👤 <b>{html.escape(trader_name)}</b>: краткий отчет",
        f"Капитал: {format_money(report['equity'])} ₽ ({format_pct(report['pnl_total_pct'])} к старту)",
        f"Кэш: {format_money(report['cash_balance'])} ₽ | Позиции: {format_money(report['positions_value'])} ₽ ({report['positions_count']})",
    ]

    if report["trades_today_count"]:
        lines.append(
            f"Сегодня: {report['trades_today_count']} сделок | купил {report['buy_count']} | продал {report['sell_count']}"
        )
        if report["recent_trades"]:
            lines.append("Последние сделки:")
            lines.extend(f"• {trade}" for trade in report["recent_trades"])
    else:
        lines.append("Сегодня: новых сделок не было.")

    if report["positions_preview"]:
        lines.append(f"Портфель: {html.escape(report['positions_preview'])}")

    return "\n".join(lines)

def notify_model_switch(current_model, next_model, reason, trader_name=None):
    trader_label = trader_name or "AI Trader"
    next_label = next_model or "нет следующей модели"
    log_event(
        f"[{trader_label}] Переключение модели: {current_model} -> {next_label}. Причина: {reason}"
    )
    send_telegram(
        f"⚠️ <b>{html.escape(trader_label)}</b>: переключение модели\n"
        f"<code>{html.escape(current_model)}</code> → <code>{html.escape(next_label)}</code>\n"
        f"Причина: {html.escape(reason)}"
    )

def call_ai_with_fallback(prompt, models_rank, trader_name=None):
    for index, model in enumerate(models_rank):
        next_model = models_rank[index + 1]['id'] if index + 1 < len(models_rank) else None
        cmd = ["gemini", "-p", prompt, "--model", model['id'], "--output-format", "json", "--approval-mode", "yolo"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if is_capacity_error(res.stdout, res.stderr):
                notify_model_switch(
                    model['id'],
                    next_model,
                    "исчерпана квота/емкость модели",
                    trader_name=trader_name,
                )
                continue
            if res.returncode != 0:
                notify_model_switch(
                    model['id'],
                    next_model,
                    f"код возврата {res.returncode}: {shorten_error(res.stderr or res.stdout or 'unknown error')}",
                    trader_name=trader_name,
                )
                continue
            out_text = json.loads(res.stdout).get("response", "")
            if "```json" in out_text: out_text = out_text.split("```json")[1].split("```")[0]
            result = json.loads(out_text)
            trader_label = trader_name or "AI Trader"
            log_event(f"[{trader_label}] Анализ успешно завершен на модели: {model['id']}")
            return result, model['id']
        except subprocess.TimeoutExpired:
            notify_model_switch(
                model['id'],
                next_model,
                "таймаут ожидания ответа модели",
                trader_name=trader_name,
            )
            continue
        except Exception as e:
            notify_model_switch(
                model['id'],
                next_model,
                f"ошибка обработки ответа: {shorten_error(str(e))}",
                trader_name=trader_name,
            )
            continue
    return None, None

def execute_trade_actions(trader_name, actions, current_cash, snapshots, model_id):
    if not actions: return
    conn = get_db_connection(); cur = conn.cursor()
    
    # Equity для лимитов
    cur.execute("SELECT SUM(quantity * avg_entry_price) FROM trading.position WHERE trader_name = %s", (trader_name,))
    pos_val = float(cur.fetchone()[0] or 0)
    equity = current_cash + pos_val
    limit_per_asset = equity * 0.15
    risk_per_trade = equity * 0.01 # Рискуем 1% капитала на сделку

    for act in actions:
        secid = act.get("secid")
        action_type = str(act.get("action")).lower()
        reason = act.get("reason", "No reason provided")
        ticker_data = snapshots.get(secid, {})
        price = ticker_data.get("price")
        indicators = ticker_data.get("indicators", {})
        
        if not price: continue

        # 1. АВТО-ВЫХОД ПО CK_STOP (Защита)
        cur.execute("SELECT quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
        pos_row = cur.fetchone()
        if pos_row and pos_row[0] > 0:
            ck_long = indicators.get("CK_STOP_LONG")
            if ck_long and price < ck_long:
                action_type = "sell"
                reason = f"STOP-LOSS: Price {price} below CK_STOP {ck_long:.2f}"

        if action_type in ["buy", "add"]:
            # СМАРТ-САЙЗИНГ ПО ATR
            atr = indicators.get("ATRr_14", price * 0.02) # Дефолт 2% если нет ATR
            # Кол-во лотов = (Риск 1%) / ATR
            qty = max(1, int(risk_per_trade / atr)) if atr > 0 else 1
            
            cost = price * qty
            # Проверка лимитов
            if current_cash < cost:
                qty = int(current_cash / price)
                cost = price * qty
            
            if qty <= 0: continue

            cur.execute("SELECT quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
            row = cur.fetchone()
            curr_qty, curr_avg = (row[0], float(row[1])) if row else (0, 0.0)
            
            if (curr_qty * curr_avg) + cost > limit_per_asset:
                log_event(f"[{trader_name}] Limit reached for {secid}")
                continue

            new_qty = curr_qty + qty
            new_avg = ((curr_qty * curr_avg) + cost) / new_qty
            
            cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (cost, trader_name))
            cur.execute("""
                INSERT INTO trading.position (trader_name, secid, quantity, avg_entry_price, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (trader_name, secid) DO UPDATE SET 
                    quantity = EXCLUDED.quantity, avg_entry_price = EXCLUDED.avg_entry_price, updated_at = NOW()
            """, (trader_name, secid, new_qty, new_avg))
            
            cur.execute("""
                INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (trader_name, secid, "BUY", qty, price, reason, model_id))
            current_cash -= cost
            log_event(f"[{trader_name}] EXECUTED BUY: {secid} x{qty} @{price}")

        elif action_type in ["sell", "close", "reduce"]:
            if not pos_row or pos_row[0] <= 0: continue
            qty_to_sell = pos_row[0] if action_type in ["sell", "close"] else max(1, pos_row[0] // 2)
            income = price * qty_to_sell
            
            cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (income, trader_name))
            if pos_row[0] - qty_to_sell <= 0:
                cur.execute("DELETE FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
            else:
                cur.execute("UPDATE trading.position SET quantity = quantity - %s WHERE trader_name = %s AND secid = %s", (qty_to_sell, trader_name, secid))
            
            cur.execute("""
                INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (trader_name, secid, "SELL", qty_to_sell, price, reason, model_id))
            current_cash += income
            log_event(f"[{trader_name}] EXECUTED SELL: {secid} x{qty_to_sell} @{price}")

    conn.commit(); cur.close(); conn.close()

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TRADERS_DATA: return
    name = sys.argv[1]
    with open(MODEL_RANK_FILE) as f: models = sorted(json.load(f)['models'], key=lambda x: x['priority'])
    market_context = load_market_context()
    snapshots = build_price_snapshot(market_context)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (name,)); cash = float(cur.fetchone()[0])
    cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
    positions = []
    for r in cur.fetchall():
        secid, qty, avg_price = r[0], r[1], float(r[2])
        curr_price = snapshots.get(secid, {}).get("price")
        pnl_pct = ((curr_price / avg_price) - 1) * 100 if curr_price and avg_price else 0.0
        positions.append({
            "secid": secid, 
            "qty": qty, 
            "avg_price": avg_price, 
            "curr_price": curr_price, 
            "pnl_pct": round(pnl_pct, 2)
        })

    # Получаем последние 3 сделки для памяти
    cur.execute("""
        SELECT action, secid, quantity, price, created_at 
        FROM trading.journal 
        WHERE trader_name = %s 
        ORDER BY created_at DESC LIMIT 3
    """, (name,))
    recent_history = []
    for r in cur.fetchall():
        recent_history.append(f"{r[4].strftime('%H:%M')} {r[0]} {r[1]} x{r[2]} @{r[3]}")
    
    cur.execute("SELECT learned_traits FROM trading.trader_config WHERE trader_name = %s", (name,)); traits = cur.fetchone()[0]

    cur.close(); conn.close()
    macro_tickers = ['USD000UTSTOM', 'BRENT', 'GLDRUB_TOM', 'NGH6']
    macro_context = {
        ticker: compact_context_payload(market_context.get(ticker))
        for ticker in macro_tickers
        if market_context.get(ticker)
    }
    stock_context = {ticker: payload for ticker, payload in market_context.items() if ticker not in macro_tickers}

    def change_score(item):
        return abs(
            item.get("day_change")
            or item.get("hour_change")
            or item.get("five_min_change")
            or 0.0
        )

    top_movers = [
        ticker
        for ticker, _payload in sorted(
            stock_context.items(),
            key=lambda pair: change_score(pair[1]),
            reverse=True,
        )[:5]
    ]
    relevant_ids = set([p['secid'] for p in positions] + top_movers)
    filtered_market = {
        ticker: compact_context_payload(stock_context[ticker])
        for ticker in sorted(relevant_ids)
        if ticker in stock_context
    }
    # ЭКСПЕРТНЫЕ ГАЙДЛАЙНЫ ДЛЯ КАЖДОГО ТРЕЙДЕРА
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
        "Index_Tracker": "Mirror market moves. Focus on Macro indicators (USD, Gold, Oil) and their correlation with stocks."
    }

    prompt_parts = [
        f"Act as {name}. DNA: {TRADERS_DATA[name]['strategy']}. Traits: {traits}. Cash: {cash}.",
        f"Portfolio (with PnL): {json.dumps(positions)}.",
        f"Recent History: {'; '.join(recent_history)}.",
        f"Macro: {json.dumps(macro_context)}.",
        f"MARKET DATA: {json.dumps(filtered_market)}.",
        f"STRATEGIC GUIDELINE: {EXPERT_GUIDES.get(name, 'Use all indicators to maximize profit.')}",
        "TECHNICAL MANUAL: ",
        "- Alligator: Jaw(Blue), Teeth(Red), Lips(Green). Open mouth = trend.",
        "- CK_STOP: Chande Kroll Stop for exits. PSAR: Parabolic SAR for trend.",
        "- TSI: True Strength Index. RVI: Relative Vigor Index. CHOP: >61 means sideways market.",
        "Each ticker contains multi-timeframe windows. Compare current_5m with current_day/week for trend alignment.",
        (
            f"1. Query 'lightrag-algo' for '{TRADERS_DATA[name]['query']}'. "
            "2. Respond ONLY raw JSON object with keys: summary, market_bias, confidence, actions, risk_notes."
        )
    ]
    prompt = " ".join(prompt_parts)
    decisions, used_model = call_ai_with_fallback(prompt, models, trader_name=name)
    if decisions is not None:
        # Исполняем сделки в БД
        execute_trade_actions(name, decisions.get("actions", []), cash, snapshots, used_model)
        
        # Индивидуальные отчеты отключены для снижения шума. Используйте сводный часовой отчет.
        # report = get_trader_report(name, snapshots)
        # send_telegram(build_trader_report_message(name, report))
    else:
        send_telegram(f"🔴 <b>{name}</b>: Ошибка! Все AI модели недоступны или превышен таймаут.")

if __name__ == "__main__":
    main()
