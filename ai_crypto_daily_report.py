import psycopg2, json, os, requests, html, io
import matplotlib.pyplot as plt
from datetime import datetime
from algo_kb_client import insert_text_to_algo_kb
from gemini_cli_runner import call_ai_json_with_fallback
from ai_context_cache import is_low_quality_context

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "crypto_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"; TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
FAILED_LESSON_MARKERS = {"error", "ai analysis failed", "analysis failed", "kb unavailable", "no data"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def call_ai_with_fallback(prompt):
    """Метод вызова ИИ с автоматическим переключением моделей."""
    models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    data, _ = call_ai_json_with_fallback(prompt, models, name="CryptoDaily", log_func=print, category="daily_report")
    return data

def fallback_lesson(trader_name, pnl_pct, trades):
    trade_count = len(trades or [])
    return {
        "work": f"{trader_name} completed the day with {trade_count} crypto trades.",
        "resume": f"Deterministic fallback audit. Day result: {pnl_pct:+.2f}%.",
        "tuning": "Keep size conservative until the next high-quality crypto audit.",
        "_failed": True,
    }

def compact_trades(trades):
    max_trades = int(os.getenv("AI_CRYPTO_DAILY_MAX_TRADES_PER_TRADER", "20"))
    return [
        {
            "secid": item.get("secid"),
            "act": item.get("act"),
            "qty": float(item.get("qty") or 0),
            "pr": item.get("pr"),
            "rs": str(item.get("rs") or "")[:180],
        }
        for item in (trades or [])[:max_trades]
    ]

def generate_batch_lessons(trader_payloads, market_summary):
    payload = []
    for item in trader_payloads:
        payload.append({
            "trader": item["name"],
            "pnl_pct": round(item["pnl_pct"], 3),
            "positions": item["positions"],
            "trades": compact_trades(item["trades"]),
        })
    prompt = f"""
    ROLE: Crypto trading league auditor.
    MARKET: {market_summary}
    TRADERS_JSON: {json.dumps(payload, ensure_ascii=False)}

    TASK:
    For each trader, produce one concrete behavioral audit and one specific tuning instruction.
    Use only provided trades, positions, PnL and market summary.

    Respond ONLY raw JSON:
    {{"traders": {{"Trader_Name": {{"work": "...", "resume": "...", "tuning": "..."}}}}}}
    """
    data = call_ai_with_fallback(prompt)
    if not isinstance(data, dict):
        return {}
    lessons = data.get("traders", data)
    return lessons if isinstance(lessons, dict) else {}

def generate_individual_lessons(trader_name, trades, positions, pnl_pct, market_summary):
    """
    Генерирует глубокий разбор работы Crypto трейдера за день.
    """
    history_str = "".join([f"- {t['act']} {t['secid']} @{t['pr']}: {t['rs']}\n" for t in trades[:10]]) if trades else "Сделок за 24ч не было."
    pos_str = ", ".join([f"{p['secid']} (PnL: {p['pnl_pct']}%)" for p in positions]) if positions else "Нет открытых позиций (100% кэш)."

    prompt = f"""
    Аналитическая служба Крипто-Лиги. Трейдер: {trader_name}. Результат: {pnl_pct:+.2f}%.
    Портфель: {pos_str}. История: {history_str}. Рынок: {market_summary}.
    ЗАДАЧА: Сделай качественный разбор работы за день.
    Respond ONLY in JSON format: {{"work": "что делал", "resume": "разбор", "tuning": "конкретная правка"}}
    """
    data = call_ai_with_fallback(prompt)
    if data:
        return data.get("work", "Наблюдение."), data.get("resume", "Анализ завершен."), data.get("tuning", "Без изменений.")
    return "Анализ временно недоступен.", "Ошибка связи со всеми ИИ-аудиторами.", "Сохранять текущую стратегию."

def generate_daily_chart(stats):
    plt.style.use('dark_background'); fig, ax = plt.subplots(figsize=(10, 7))
    stats_sorted = sorted(stats, key=lambda x: x['name'])
    names = [s['name'].replace('_', '\n') for s in stats_sorted]
    pcts = [s['pct'] for s in stats_sorted]
    colors = ['#f59e0b' if p >= 0 else '#fb7185' for p in pcts]
    bars = ax.bar(names, pcts, color=colors, edgecolor='white', linewidth=0.7)
    ax.axhline(0, color='white', linewidth=1)
    ax.set_title('CRYPTO AI LEAGUE: DAILY PERFORMANCE', fontsize=16, color='#f59e0b', fontweight='bold', pad=30)
    for bar in bars:
        h = bar.get_height(); ax.text(bar.get_x()+bar.get_width()/2., h+(0.1 if h>=0 else -0.8), f'{h:+.2f}%', ha='center', va='bottom' if h>=0 else 'top', color='white', fontsize=9, fontweight='bold')
    plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=120); buf.seek(0); plt.close(fig)
    return buf

def send_telegram_package(caption, message, photo_bytes):
    if not TELEGRAM_TOKEN: return
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url_photo, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}, files={'photo': ('daily.png', photo_bytes, 'image/png')}, proxies=PROXIES, timeout=30)
    lessons = message.split("\n\n")
    for i in range(0, len(lessons), 5):
        chunk = "\n\n".join(lessons[i:i+5])
        if chunk.strip(): requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'HTML'}, proxies=PROXIES, timeout=30)

def save_to_knowledge_base(content, trader_name):
    """Отправляет аналитический отчет в LightRAG (ALGO) для обучения."""
    if is_low_quality_context(content):
        print(f"Skipped low-quality crypto daily KB upload for {trader_name}.")
        return False
    try:
        insert_text_to_algo_kb(
            f"TRADER EVOLUTION DATA: {trader_name}. Date: {datetime.now().strftime('%Y-%m-%d')}. Analysis: {content}",
            file_source=f"crypto_daily_{trader_name}_{datetime.now().strftime('%Y-%m-%d')}.txt",
            log_func=print,
        )
        return True
    except Exception as exc:
        print(f"ALGO KB crypto daily upload failed for {trader_name}: {exc}")
        return False

def generate_report():
    from crypto_research_context import build_price_snapshot, load_market_context
    conn = get_db_connection(); cur = conn.cursor()
    market_context = load_market_context(conn)
    prices = {secid: payload["price"] for secid, payload in build_price_snapshot(market_context).items()}

    # Контекст крипторынка
    btc_change = market_context.get('BTC/USDT', {}).get('day_change', 0)
    market_summary = f"Биткоин: {btc_change:+.2f}%. "

    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders_raw = cur.fetchall()
    max_traders = int(os.getenv("AI_CRYPTO_DAILY_REPORT_MAX_TRADERS", "0") or "0")
    if max_traders > 0:
        traders_raw = traders_raw[:max_traders]
    league_stats = []; total_trades = 0; lessons_list = []; trader_payloads = []

    for name, cash in traders_raw:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity != 0", (name,))
        positions = []
        for r in cur.fetchall():
            secid, qty, avg_p = r[0], r[1], float(r[2])
            curr_p = prices.get(secid, avg_p)
            pnl = ((curr_p / avg_p) - 1) * 100 if avg_p else 0
            positions.append({"secid": secid, "qty": qty, "pnl_pct": round(pnl, 2)})

        pos_val = sum([abs(p["qty"]) * prices.get(p["secid"], 0) for p in positions])
        equity = float(cash) + pos_val

        cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        total_trades += cur.fetchone()[0]

        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 100.0
        profit_pct = ((equity / sod) - 1) * 100
        league_stats.append({"name": name, "equity": equity, "pct": profit_pct, "sod": sod})

        cur.execute("SELECT secid, action, quantity, price, reason FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades = [{"secid": r[0], "act": r[1], "qty": r[2], "pr": float(r[3]), "rs": r[4]} for r in cur.fetchall()]
        trader_payloads.append({
            "name": name,
            "positions": positions,
            "trades": trades,
            "pnl_pct": profit_pct,
        })

    lessons_by_trader = generate_batch_lessons(trader_payloads, market_summary)
    for payload in trader_payloads:
        name = payload["name"]
        profit_pct = payload["pnl_pct"]
        res = lessons_by_trader.get(name) if isinstance(lessons_by_trader, dict) else None
        if not isinstance(res, dict):
            res = fallback_lesson(name, profit_pct, payload["trades"])
        failed = bool(res.get("_failed"))
        for key in ("work", "resume", "tuning"):
            value = res.get(key)
            if value is None or not str(value).strip():
                res[key] = fallback_lesson(name, profit_pct, payload["trades"])[key]
                failed = True
        if any(str(res.get(key, "")).strip().lower() in FAILED_LESSON_MARKERS for key in ("work", "resume", "tuning")):
            failed = True
        work, resume, tuning = str(res["work"]), str(res["resume"]), str(res["tuning"])
        cur.execute("UPDATE trading.trader_config SET learned_traits = %s, updated_at = NOW() WHERE trader_name = %s", (tuning, name))
        lessons_list.append(f"👤 <b>{html.escape(name)}</b> ({profit_pct:+.2f}%)\n📝 <b>Работа:</b> {html.escape(work)}\n✅ <b>Резюме:</b> {html.escape(resume)}\n🔧 <b>Тюнинг:</b> {html.escape(tuning)}")
        if not failed:
            save_to_knowledge_base(f"Work: {work}\nResume: {resume}\nTuning: {tuning}", name)

    conn.commit()
    total_equity = sum(s['equity'] for s in league_stats); total_sod = sum(s['sod'] for s in league_stats)
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else 0.0
    chart_bytes = generate_daily_chart(league_stats)
    caption = f"🏆 <b>DAILY SUMMARY | CRYPTO LEAGUE</b>\n💰 Капитал Лиги: <b>{total_equity:,.0f} $</b>\n📊 Тренд дня: <b>{total_pct:+.2f}%</b>\n🔄 Сделок: <b>{total_trades}</b>"
    send_telegram_package(caption, "\n\n".join(lessons_list), chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__":
    generate_report()
