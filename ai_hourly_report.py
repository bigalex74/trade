import psycopg2
import os
import requests
import json
import matplotlib.pyplot as plt
import io
from datetime import datetime

from market_research_context import build_price_snapshot, load_market_context

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Force load from .env if missing (for reliable daemon execution)
if not TELEGRAM_TOKEN and os.path.exists("/home/user/.env"):
    with open("/home/user/.env") as f:
        for line in f:
            if "TELEGRAM_BOT_TOKEN=" in line:
                TELEGRAM_TOKEN = line.split("=")[1].strip()

PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def send_telegram_photo(message, photo_bytes):
    if not TELEGRAM_TOKEN: 
        print("Error: No TELEGRAM_BOT_TOKEN found in env.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    # Correct way to send photo with caption
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': message, 'parse_mode': 'HTML'}
    
    try:
        response = requests.post(url, data=payload, files=files, proxies=PROXIES, timeout=30)
        if response.status_code != 200:
            print(f"Telegram API Error: {response.status_code} - {response.text}")
        else:
            print("Successfully sent photo to Telegram.")
    except Exception as e:
        print(f"Failed to send photo: {e}")

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def generate_banana_graph(stats):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Sort for chart
    stats_sorted = sorted(stats, key=lambda x: x['pct'])
    
    names = [s['name'].replace('_', '\n') for s in stats_sorted]
    pcts = [s['pct'] for s in stats_sorted]
    colors = ['#4ade80' if p >= 0 else '#f87171' for p in pcts]
    
    bars = ax.barh(names, pcts, color=colors)
    ax.set_xlabel('Прибыль / Убыток (%)', fontsize=10, color='white')
    ax.set_title('MOEX AI LEAGUE: PERFORMANCE', fontsize=14, color='#3b82f6', fontweight='bold', pad=20)
    
    for bar in bars:
        width = bar.get_width()
        label_x_pos = width + 0.05 if width >= 0 else width - 0.05
        ha = 'left' if width >= 0 else 'right'
        ax.text(label_x_pos, bar.get_y() + bar.get_height()/2, f'{width:+.2f}%', 
                va='center', ha=ha, color='white', fontsize=9)
                
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120)
    buf.seek(0)
    plt.close(fig)
    return buf

def main():
    conn = get_db_connection(); cur = conn.cursor()
    prices = {secid: payload["price"] for secid, payload in build_price_snapshot(load_market_context(conn)).items()}
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders = cur.fetchall()
    
    stats = []
    for name, cash in traders:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
        pos_val = sum([r[1] * prices.get(r[0], float(r[2])) for r in cur.fetchall()])
        equity = float(cash) + pos_val
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 10000.0
        
        profit = equity - sod
        profit_pct = (profit / sod) * 100
        stats.append({"name": name, "equity": equity, "profit": profit, "pct": profit_pct, "sod": sod})
    
    total_equity = sum(s['equity'] for s in stats)
    total_sod = sum(s['sod'] for s in stats)
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else 0.0
    
    stats_text = sorted(stats, key=lambda x: x['profit'], reverse=True)
    chart_bytes = generate_banana_graph(stats)
    
    report = f"⏱ <b>ЧАСОВОЙ ОТЧЕТ ЛИГИ</b>\n⎯⎯⎯\n"
    for i, t in enumerate(stats_text[:3]):
        icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
        report += f"{icon} {t['name']}: {t['equity']:,.2f} ({t['pct']:+.2f}%)\n"
    
    trend_icon = "📈" if total_pct >= 0 else "📉"
    report += f"⎯⎯⎯\n"
    report += f"💰 <b>ОБЩИЙ КАПИТАЛ: {total_equity:,.2f} ₽</b>\n"
    report += f"📊 Тренд дня: {total_pct:+.2f}% {trend_icon}"
        
    send_telegram_photo(report, chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
