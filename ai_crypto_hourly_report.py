import psycopg2, os, requests, json, io, html
import matplotlib.pyplot as plt
from datetime import datetime

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "crypto_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram_photo(caption, photo_bytes):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}, 
                  files={'photo': ('chart.png', photo_bytes, 'image/png')}, proxies=PROXIES, timeout=30)

def generate_banana_graph(stats):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    stats_sorted = sorted(stats, key=lambda x: x['pct'])
    names = [s['name'].replace('_', '\n') for s in stats_sorted]
    pcts = [s['pct'] for s in stats_sorted]
    colors = ['#f59e0b' if p >= 0 else '#ef4444' for p in pcts]
    bars = ax.barh(names, pcts, color=colors)
    ax.set_xlabel('Profit / Loss (%)', fontsize=10, color='white')
    ax.set_title('CRYPTO AI LEAGUE: PERFORMANCE', fontsize=14, color='#f59e0b', fontweight='bold', pad=20)
    for bar in bars:
        width = bar.get_width()
        ax.text(width + (0.05 if width>=0 else -0.05), bar.get_y() + bar.get_height()/2, f'{width:+.2f}%', va='center', color='white', fontsize=9)
    plt.tight_layout()
    buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=120); buf.seek(0); plt.close(fig)
    return buf

def main():
    from crypto_research_context import build_price_snapshot, load_market_context
    conn = get_db_connection(); cur = conn.cursor()
    prices = {secid: payload["price"] for secid, payload in build_price_snapshot(load_market_context(conn)).items()}
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders = cur.fetchall()
    stats = []
    for name, cash in traders:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity != 0", (name,))
        pos_val = sum([abs(r[1]) * prices.get(r[0], float(r[2])) for r in cur.fetchall()])
        equity = float(cash) + pos_val
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 100.0
        profit_pct = ((equity / sod) - 1) * 100 if sod else 0.0
        stats.append({"name": name, "equity": equity, "pct": profit_pct, "sod": sod})
    total_equity = sum(s['equity'] for s in stats); total_sod = sum(s['sod'] for s in stats)
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else 0.0
    chart_bytes = generate_banana_graph(stats)
    report = f"🪙 <b>ЧАСОВОЙ ОТЧЕТ CRYPTO</b>\n⎯⎯⎯\n"
    stats_text = sorted(stats, key=lambda x: x['pct'], reverse=True)
    for i, t in enumerate(stats_text[:3]):
        icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
        report += f"{icon} {t['name']}: {t['equity']:,.2f} $ ({t['pct']:+.2f}%)\n"
    trend_icon = "📈" if total_pct >= 0 else "📉"
    report += f"⎯⎯⎯\n💰 <b>ОБЩИЙ КАПИТАЛ: {total_equity:,.2f} $</b>\n📊 Trend: {total_pct:+.2f}% {trend_icon}"
    send_telegram_photo(report, chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__": main()
