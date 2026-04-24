import psycopg2
import os
import requests
import json
import matplotlib.pyplot as plt
import io
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from market_research_context import build_price_snapshot, load_market_context

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_CHAT_ID = "923741104"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram_photo(message, photo_bytes):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload, files=files, proxies=PROXIES, timeout=30)
    except Exception as e:
        print(f"Failed to send photo: {e}")

def get_hourly_trades_count(cur):
    """Считает количество исполненных сделок за последний час."""
    cur.execute("""
        SELECT count(*) 
        FROM trading.journal 
        WHERE created_at > now() - interval '1 hour'
          AND action IN ('BUY', 'SELL', 'SHORT', 'COVER')
    """)
    return cur.fetchone()[0]

def generate_cumulative_chart(history_points):
    """
    Рисует график изменения общего эквити лиги с начала дня.
    history_points: список кортежей (time, total_equity)
    """
    if not history_points: return None
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5))
    
    times = [p[0] for p in history_points]
    values = [float(p[1]) for p in history_points]
    
    ax.plot(times, values, color='#3b82f6', linewidth=2, marker='o', markersize=4, label='Total Equity')
    ax.fill_between(times, values, min(values)*0.999, color='#3b82f6', alpha=0.1)
    
    # Горизонтальная линия начала дня
    sod_value = values[0]
    ax.axhline(y=sod_value, color='#94a3b8', linestyle='--', alpha=0.5, label='Start of Day')
    
    ax.set_title('MOEX AI LEAGUE: INTRADAY DYNAMICS', fontsize=12, color='#3b82f6', fontweight='bold')
    ax.grid(True, alpha=0.1)
    plt.xticks(rotation=45)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def main():
    conn = get_db_connection(); cur = conn.cursor()
    
    # 1. Текущие цены и портфель
    prices = {secid: Decimal(str(payload["price"])) for secid, payload in build_price_snapshot(load_market_context(conn)).items()}
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio")
    portfolio_rows = cur.fetchall()
    
    stats = []
    total_equity = Decimal("0.0")
    
    for name, cash in portfolio_rows:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
        pos_val = sum([Decimal(str(r[1])) * prices.get(r[0], Decimal(str(r[2]))) for r in cur.fetchall()], Decimal("0.0"))
        equity = Decimal(str(cash)) + pos_val
        
        # Получаем значение на начало дня (SOD) из вчерашнего снапшота
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone()
        sod = Decimal(str(row[0])) if row else Decimal("10000.0")
        
        total_equity += equity
        stats.append({"name": name, "equity": equity, "sod": sod})

    # 2. История для графика (общий баланс лиги с начала дня)
    # Мы берем текущий total_equity как финальную точку, а промежуточные - из логов или аппроксимируем
    # Для версии 0.8.2 мы будем использовать таблицу daily_stats + текущий момент
    # В будущем здесь будет запрос к таблице истории эквити
    history_points = []
    total_sod = sum(s['sod'] for s in stats)
    
    # Точка 1: 10:00 (Начало дня)
    start_time = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    history_points.append((start_time, total_sod))
    
    # Точка 2: Текущий момент
    history_points.append((datetime.now(), total_equity))
    
    # 3. Счетчик сделок
    trades_count = get_hourly_trades_count(cur)
    
    # 4. Формирование отчета
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else Decimal("0.0")
    chart_bytes = generate_cumulative_chart(history_points)
    
    report = [
        f"⏱ <b>ЧАСОВОЙ ОТЧЕТ ЛИГИ</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Капитал:</b> {float(total_equity):,.2f} ₽",
        f"📈 <b>Тренд дня:</b> {float(total_pct):+.2f}%",
        f"🔄 <b>Сделок за час:</b> {trades_count}",
        f"\n🏆 <b>ТОП ТРЕЙДЕРОВ:</b>"
    ]
    
    for i, t in enumerate(sorted(stats, key=lambda x: x['equity']/x['sod'], reverse=True)[:3]):
        pct = ((t['equity'] / t['sod']) - 1) * 100
        icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
        report.append(f"{icon} <code>{t['name']:<14}</code>: {float(pct):+.2f}%")

    send_telegram_photo("\n".join(report), chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
