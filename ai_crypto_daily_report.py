import psycopg2, json, subprocess, os, requests, html, io
import matplotlib.pyplot as plt
from datetime import datetime

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "crypto_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"; TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def generate_individual_lessons(trader_name, trades):
    if not trades: return "Работа: Наблюдение.\nРезюме: Сделок нет.\nТюнинг: Без изменений."
    history_str = "".join([f"- {t['act']} {t['secid']} @{t['pr']}: {t['rs']}\n" for t in trades[:5]])
    prompt = f"Анализ Crypto трейдера {trader_name}. Сделки: {history_str}. ЗАДАЧА: Очень короткий отчет (Работа, Резюме, Тюнинг) на РУССКОМ."
    cmd = ["gemini", "-p", prompt, "--approval-mode", "yolo", "--output-format", "json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return json.loads(res.stdout).get("response", "Анализ недоступен.").strip()
    except: return "Анализ временно недоступен."

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
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}, files={'photo': ('daily.png', photo_bytes, 'image/png')}, proxies=PROXIES, timeout=30)
    lessons = message.split("\n\n")
    for i in range(0, len(lessons), 5):
        chunk = "\n\n".join(lessons[i:i+5])
        if chunk.strip(): requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'HTML'}, proxies=PROXIES, timeout=30)

def generate_report():
    from crypto_research_context import build_price_snapshot, load_market_context
    conn = get_db_connection(); cur = conn.cursor()
    prices = {secid: payload["price"] for secid, payload in build_price_snapshot(load_market_context(conn)).items()}
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders_raw = cur.fetchall()
    league_stats = []; total_trades = 0; lessons_list = []
    for name, cash in traders_raw:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity != 0", (name,))
        pos_val = sum([abs(r[1]) * prices.get(r[0], float(r[2])) for r in cur.fetchall()])
        equity = float(cash) + pos_val
        cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades_count = cur.fetchone()[0]; total_trades += trades_count
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 100.0
        profit_pct = ((equity / sod) - 1) * 100
        league_stats.append({"name": name, "equity": equity, "pct": profit_pct, "sod": sod})
        cur.execute("SELECT secid, action, quantity, price, reason FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades = [{"secid": r[0], "act": r[1], "qty": r[2], "pr": float(r[3]), "rs": r[4]} for r in cur.fetchall()]
        report_text = generate_individual_lessons(name, trades)
        cur.execute("UPDATE trading.trader_config SET learned_traits = %s, updated_at = NOW() WHERE trader_name = %s", (report_text, name))
        lessons_list.append(f"👤 <b>{html.escape(name)}</b> ({profit_pct:+.2f}%)\n{html.escape(report_text)}")
    
    stats_sorted = sorted(league_stats, key=lambda x: x['pct'], reverse=True)
    top_3 = [s for s in stats_sorted[:3] if s['pct'] > 0]; losers = [s for s in stats_sorted if s['pct'] < 0]
    bonus_pool = 0.0; reallocation_notes = []
    if top_3 and losers:
        for loser in losers:
            cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (loser['name'],))
            loser_cash = float(cur.fetchone()[0])
            if loser_cash > 10:
                penalty = loser_cash * 0.05; cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (penalty, loser['name']))
                bonus_pool += penalty; reallocation_notes.append(f"🔻 Изъято {penalty:,.1f} $ у {loser['name']}")
        if bonus_pool > 0:
            bonus_per_leader = bonus_pool / len(top_3)
            for leader in top_3:
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (bonus_per_leader, leader['name']))
                reallocation_notes.append(f"🏆 Бонус {bonus_per_leader:,.1f} $ для {leader['name']}")
    
    conn.commit(); total_equity = sum(s['equity'] for s in league_stats); total_sod = sum(s['sod'] for s in league_stats)
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else 0.0
    chart_bytes = generate_daily_chart(league_stats)
    alloc_str = ("\n\n⚖️ <b>АЛЛОКАЦИЯ КАПИТАЛА</b>\n" + "\n".join(reallocation_notes)) if reallocation_notes else ""
    caption = f"🏆 <b>DAILY SUMMARY | CRYPTO LEAGUE</b>\n💰 Капитал Лиги: <b>{total_equity:,.0f} $</b>\n📊 Тренд дня: <b>{total_pct:+.2f}%</b>\n🔄 Сделок: <b>{total_trades}</b>"
    send_telegram_package(caption, "\n\n".join(lessons_list) + alloc_str, chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__": generate_report()
