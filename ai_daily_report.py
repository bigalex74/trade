import psycopg2, json, os, requests, html, io
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from algo_kb_client import insert_text_to_algo_kb
from gemini_cli_runner import call_ai_json_with_fallback, call_ai_markdown_with_fallback

# CONFIG
DB_CONFIG = {"host": os.getenv("DB_HOST", "localhost"), "database": "market_research", "user": os.getenv("DB_USER", "n8n_user"), "password": os.getenv("DB_PASSWORD", "n8n_db_password")}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KB_ALGO_URL = "http://localhost:9624/query"
KB_GENERAL_URL = "http://localhost:9622/query"
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
FAILED_LESSON_MARKERS = {"error", "ai analysis failed", "analysis failed", "kb unavailable", "no data"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def query_kb(url, query):
    try:
        resp = requests.post(url, json={"query": query, "mode": "hybrid"}, auth=('bigalex', 'qQ08102003'), timeout=30)
        return resp.json().get("response", "No data.")
    except: return "KB Unavailable."

def call_ai_with_fallback(prompt, name="MoexDaily"):
    models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    data, _ = call_ai_json_with_fallback(prompt, models, name=name, log_func=print, category="daily_report")
    return data

def fallback_lesson(trader_name, pnl_pct, trades):
    trade_count = len(trades or [])
    direction = "положительным" if pnl_pct >= 0 else "отрицательным"
    return {
        "work": f"{trader_name}: день завершен с {direction} результатом, сделок за период: {trade_count}.",
        "resume": "Надежный AI-разбор недоступен; в отчет включен deterministic-аудит.",
        "tuning": "Держать размер позиции консервативным до следующего качественного аудита.",
        "_failed": True,
    }

def compact_trades(trades):
    max_trades = int(os.getenv("AI_DAILY_REPORT_MAX_TRADES_PER_TRADER", "20"))
    compacted = []
    for item in (trades or [])[:max_trades]:
        compacted.append({
            "a": item.get("a"),
            "s": item.get("s"),
            "p": item.get("p"),
            "r": str(item.get("r") or "")[:180],
        })
    return compacted

def generate_batch_lessons(trader_payloads, market_summary, alpha_context):
    if os.getenv("AI_DAILY_REPORT_SKIP_AI", "0") == "1":
        return {}
    prompt_payload = []
    for payload in trader_payloads:
        prompt_payload.append({
            "trader": payload["name"],
            "pnl_pct": round(payload["pnl_pct"], 3),
            "positions": payload["positions"],
            "trades": compact_trades(payload["trades"]),
        })
    prompt = f"""
    ROLE: Senior trading league auditor.
    MARKET: {market_summary}
    STRATEGIC_ALPHA: {str(alpha_context)[:4000]}
    TRADERS_JSON: {json.dumps(prompt_payload, ensure_ascii=False)}

    TASK:
    For each trader, produce one concrete behavioral audit and one specific tuning instruction.
    Preserve strategy quality: do not invent trades, use only provided positions/trades/PnL and alpha context.

    Respond ONLY raw JSON:
    {{"traders": {{"Trader_Name": {{"work": "...", "resume": "...", "tuning": "..."}}}}}}
    """
    data = call_ai_with_fallback(prompt, name="MoexDailyBatch")
    if not isinstance(data, dict):
        return {}
    lessons = data.get("traders", data)
    return lessons if isinstance(lessons, dict) else {}

def generate_individual_lessons(trader_name, trades, positions, pnl_pct, market_summary, alpha_context):
    prompt = f"""
    ROLE: Senior Auditor. Trader: {trader_name}. Day PnL: {pnl_pct:+.2f}%.
    Positions: {positions}. Trades: {trades}. Market: {market_summary}.
    STRATEGIC ALPHA: {alpha_context}
    TASK: Deep analysis of behavior and 1-sentence specific tuning instruction.
    Respond ONLY in JSON: {{"work": "...", "resume": "...", "tuning": "..."}}
    """
    data = call_ai_with_fallback(prompt)
    if not isinstance(data, dict):
        return {
            "work": "AI analysis failed",
            "resume": "AI analysis failed",
            "tuning": "No tuning generated",
            "_failed": True,
        }
    for key in ("work", "resume", "tuning"):
        value = data.get(key)
        if value is None or not str(value).strip():
            data[key] = "AI analysis failed"
            data["_failed"] = True
    data["_failed"] = data.get("_failed", False) or any(
        str(data.get(key, "")).strip().lower() in FAILED_LESSON_MARKERS
        for key in ("work", "resume", "tuning")
    )
    return data

def generate_staff_suggestions(nightly_context):
    if os.getenv("AI_DAILY_REPORT_SKIP_AI", "0") == "1":
        return (
            "AI-аудит пропущен; отправлен deterministic fallback-отчет. "
            "Риск держать консервативным, постмаркет-логи проверить перед изменением стратегий."
        )
    prompt = f"""
    ROLE: Staff Engineer & Hedge Fund Manager.
    CONTEXT FROM NIGHTLY ANALYTICS: {nightly_context}
    TASK: Provide 1-2 HIGH-LEVEL recommendations to improve the trading league (technical or algorithmic).
    FORMAT: 2 short bullet points.
    """
    data, _ = call_ai_markdown_with_fallback(
        prompt,
        ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
        name="MoexDailyStaff",
        log_func=print,
        category="daily_report",
    )
    return data or "Сохранять текущий стабильный режим."

def generate_daily_chart(stats):
    plt.style.use('dark_background'); fig, ax = plt.subplots(figsize=(10, 7))
    stats_sorted = sorted(stats, key=lambda x: x['name'])
    names = [s['name'].replace('_', '\n') for s in stats_sorted]
    pcts = [s['pct'] for s in stats_sorted]
    colors = ['#34d399' if p >= 0 else '#fb7185' for p in pcts]
    bars = ax.bar(names, pcts, color=colors, edgecolor='white', linewidth=0.7)
    ax.axhline(0, color='white', linewidth=1)
    ax.set_title('ИТОГОВЫЙ ОТЧЕТ ПО ТРЕЙДЕРАМ', fontsize=16, color='#60a5fa', fontweight='bold', pad=30)
    for bar in bars:
        h = bar.get_height(); ax.text(bar.get_x()+bar.get_width()/2., h+(0.1 if h>=0 else -0.8), f'{h:+.2f}%', ha='center', va='bottom' if h>=0 else 'top', color='white', fontsize=9, fontweight='bold')
    plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=120); buf.seek(0); plt.close(fig)
    return buf

def generate_report():
    test_mode = os.getenv("AI_TEST_MODE", "0") == "1"
    from market_research_context import build_price_snapshot, load_market_context
    conn = get_db_connection(); cur = conn.cursor()
    m_ctx = load_market_context(conn); prices = {s: p["price"] for s, p in build_price_snapshot(m_ctx).items()}

    # 1. Сбор ночного контекста
    alpha_ctx = query_kb(KB_ALGO_URL, "Summary of tonight's Strategic Alpha and patterns.")
    tech_ctx = query_kb(KB_GENERAL_URL, "Summary of tonight's Technical SRE Audit.")

    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders_raw = cur.fetchall()
    max_traders = int(os.getenv("AI_DAILY_REPORT_MAX_TRADERS", "0") or "0")
    if max_traders > 0:
        traders_raw = traders_raw[:max_traders]
    league_stats = []; lessons_list = []; trader_payloads = []
    failed_lessons = 0

    for name, cash in traders_raw:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
        positions = [{"s": r[0], "q": r[1], "pnl": round(((prices.get(r[0], float(r[2]))/float(r[2]))-1)*100, 2)} for r in cur.fetchall()]
        cur.execute("SELECT action, secid, price, reason FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades = [{"a": r[0], "s": r[1], "p": float(r[2]), "r": r[3]} for r in cur.fetchall()]

        # Получаем данные о капитале на начало дня
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 10000.0
        equity = float(cash) + sum([p["q"] * prices.get(p["s"], 0) for p in positions])
        profit_pct = ((equity / sod) - 1) * 100
        league_stats.append({"name": name, "equity": equity, "pct": profit_pct})
        trader_payloads.append({
            "name": name,
            "positions": positions,
            "trades": trades,
            "pnl_pct": profit_pct,
        })

    lessons_by_trader = generate_batch_lessons(trader_payloads, "Дневная сводка IMOEX", alpha_ctx)
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
        res["_failed"] = failed
        failed_lessons += int(failed)
        lessons_list.append(
            f"👤 <b>{html.escape(name)}</b> ({profit_pct:+.2f}%)\n"
            f"📝 <b>Работа:</b> {html.escape(str(res['work']))}\n"
            f"✅ <b>Резюме:</b> {html.escape(str(res['resume']))}\n"
            f"🔧 <b>Тюнинг:</b> {html.escape(str(res['tuning']))}"
        )

    # 2. Финальные предложения
    suggestions = generate_staff_suggestions(f"Alpha: {alpha_ctx}. Tech: {tech_ctx}")

    # 3. Отправка
    chart = generate_daily_chart(league_stats)
    caption = f"🏆 <b>ИТОГОВЫЙ ОТЧЕТ ПО MOEX AI ЛИГЕ</b>\n📊 Трейдеров в анализе: {len(league_stats)}\n🔄 Ночной цикл: завершен"
    full_message = "\n\n".join(lessons_list) + f"\n\n💡 <b>РЕКОМЕНДАЦИИ ШТАБА:</b>\n{html.escape(str(suggestions))}"
    max_failed = int(os.getenv("AI_DAILY_REPORT_MAX_FAILED_TRADERS", "0") or "0")
    if max_failed <= 0:
        max_failed = max(1, int(len(league_stats) * float(os.getenv("AI_DAILY_REPORT_MAX_FAILED_RATIO", "0.25"))))
    quality_ok = failed_lessons <= max_failed
    if not quality_ok:
        warning = (
            f"⚠️ <b>КАЧЕСТВО AI-РАЗБОРА СНИЖЕНО</b>\n"
            f"AI-разбор не получен для {failed_lessons}/{len(league_stats)} трейдеров. "
            "В Telegram отправлен fallback-отчет; загрузка в ALGO KB пропущена."
        )
        caption = f"{caption}\n⚠️ AI-разбор деградировал"
        full_message = f"{warning}\n\n{full_message}"
        print(
            f"Daily report quality gate failed: failed_lessons={failed_lessons}, "
            f"max_failed={max_failed}, traders={len(league_stats)}. Sending Telegram fallback and skipping ALGO KB upload."
        )

    url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    if TELEGRAM_TOKEN and not test_mode:
        resp = requests.post(url_photo, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}, files={'photo': ('daily.png', chart, 'image/png')}, proxies=PROXIES, timeout=30)
        print(f"Telegram photo status={resp.status_code}")
    else:
        print("Telegram send skipped.")

    if not test_mode and quality_ok:
        try:
            insert_text_to_algo_kb(
                f"{caption}\n\n{full_message}",
                file_source=f"moex_daily_report_{datetime.now().strftime('%Y-%m-%d')}.txt",
                log_func=print,
            )
        except Exception as exc:
            print(f"ALGO KB daily report upload failed: {exc}")
    elif not quality_ok:
        print("ALGO KB daily report upload skipped: quality gate failed.")
    else:
        print("AI_TEST_MODE=1: skipped ALGO KB daily report upload.")

    for i in range(0, len(full_message.split("\n\n")), 5):
        chunk = "\n\n".join(full_message.split("\n\n")[i:i+5])
        if TELEGRAM_TOKEN and not test_mode:
            resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'HTML'}, proxies=PROXIES, timeout=30)
            print(f"Telegram chunk status={resp.status_code} chars={len(chunk)}")
        else:
            print(f"Telegram chunk skipped: {len(chunk)} chars")

    cur.close(); conn.close()

if __name__ == "__main__":
    generate_report()
