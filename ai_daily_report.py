import psycopg2
import json
import subprocess
import os
import requests
import html
import matplotlib.pyplot as plt
import io
from datetime import datetime

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

def generate_individual_lessons(trader_name, trades):
    """
    Генерирует короткую выжимку в 3 пункта.
    """
    if not trades:
        return "📝 Работа: Наблюдение за рынком.\n✅ Резюме: Сделок нет.\n🔧 Тюнинг: Сохранять текущий промпт."

    history_str = ""
    for t in trades[:5]: # Берем последние 5 для краткости
        history_str += f"- {t['act']} {t['secid']} @{t['pr']}: {t['rs']}\n"

    prompt = f"""
    Анализ трейдера {trader_name}.
    Сделки за 24ч:
    {history_str}
    
    ЗАДАЧА: Напиши ОЧЕНЬ короткий отчет (до 10 слов на пункт) на РУССКОМ:
    1. 'Работа': (что делал)
    2. 'Резюме': (результат/качество)
    3. 'Тюнинг': (короткая правка для промпта)
    
    Формат:
    Работа: <текст>
    Резюме: <текст>
    Тюнинг: <текст>
    """
    cmd = ["gemini", "-p", prompt, "--approval-mode", "yolo", "--output-format", "json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = json.loads(res.stdout).get("response", "Анализ недоступен.")
        return out.strip()
    except:
        return "Анализ временно недоступен."

def generate_daily_chart(stats):
    """
    Вертикальный график, визуально отличный от часового.
    """
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 7))
    
    stats_sorted = sorted(stats, key=lambda x: x['name'])
    names = [s['name'].replace('_', '\n') for s in stats_sorted]
    pcts = [s['pct'] for s in stats_sorted]
    colors = ['#34d399' if p >= 0 else '#fb7185' for p in pcts] # Мятный и розовый
    
    bars = ax.bar(names, pcts, color=colors, edgecolor='white', linewidth=0.7)
    ax.axhline(0, color='white', linewidth=1)
    ax.set_title('MOEX AI LEAGUE: DAILY PERFORMANCE', fontsize=16, color='#60a5fa', fontweight='bold', pad=30)
    ax.set_ylabel('Прибыль / Убыток (%)', color='gray')
    ax.grid(axis='y', linestyle=':', alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + (0.1 if height >= 0 else -0.8),
                f'{height:+.2f}%', ha='center', va='bottom' if height >= 0 else 'top', 
                color='white', fontsize=9, fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=120); buf.seek(0); plt.close(fig)
    return buf

def send_telegram_package(caption, message, photo_bytes):
    if not TELEGRAM_TOKEN: return
    # 1. Фото
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url_photo, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}, 
                  files={'photo': ('daily.png', photo_bytes, 'image/png')}, proxies=PROXIES, timeout=30)
    
    # 2. Текст (делим на части по 5 трейдеров)
    lessons = message.split("\n\n")
    for i in range(0, len(lessons), 5):
        chunk = "\n\n".join(lessons[i:i+5])
        if not chunk.strip(): continue
        url_text = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url_text, json={'chat_id': TELEGRAM_CHAT_ID, 'text': chunk, 'parse_mode': 'HTML'}, 
                      proxies=PROXIES, timeout=30)

def generate_report():
    conn = get_db_connection(); cur = conn.cursor()
    prices = {secid: payload["price"] for secid, payload in build_price_snapshot(load_market_context(conn)).items()}
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio"); traders_raw = cur.fetchall()
    
    league_stats = []
    total_trades = 0
    lessons_list = []
    
    for name, cash in traders_raw:
        cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0", (name,))
        pos_val = sum([r[1] * prices.get(r[0], float(r[2])) for r in cur.fetchall()])
        equity = float(cash) + pos_val
        
        cur.execute("SELECT count(*) FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades_count = cur.fetchone()[0]
        total_trades += trades_count
        
        cur.execute("SELECT total_value FROM trading.daily_stats WHERE trader_name = %s ORDER BY stat_date DESC LIMIT 1", (name,))
        row = cur.fetchone(); sod = float(row[0]) if row else 10000.0
        
        profit_pct = ((equity / sod) - 1) * 100
        league_stats.append({"name": name, "equity": equity, "pct": profit_pct, "sod": sod})

        # Индивидуальный отчет
        cur.execute("SELECT secid, action, quantity, price, reason FROM trading.journal WHERE trader_name = %s AND created_at > now() - interval '24 hours'", (name,))
        trades = [{"secid": r[0], "act": r[1], "qty": r[2], "pr": float(r[3]), "rs": r[4]} for r in cur.fetchall()]
        
        report_text = generate_individual_lessons(name, trades)
        
        # СОХРАНЕНИЕ ЭВОЛЮЦИИ: Обновляем ДНК трейдера
        cur.execute("UPDATE trading.trader_config SET learned_traits = %s, updated_at = NOW() WHERE trader_name = %s", (report_text, name))
        
        lessons_list.append(f"👤 <b>{html.escape(name)}</b> ({profit_pct:+.2f}%)\n{html.escape(report_text)}")

    conn.commit() # Фиксируем все изменения памяти
    total_equity = sum(s['equity'] for s in league_stats)
    total_sod = sum(s['sod'] for s in league_stats)
    total_pct = ((total_equity / total_sod) - 1) * 100 if total_sod else 0.0
    
    chart_bytes = generate_daily_chart(league_stats)
    
    caption = (
        f"🏆 <b>DAILY SUMMARY | MOEX AI LEAGUE</b>\n"
        f"💰 Капитал Лиги: <b>{total_equity:,.0f} ₽</b>\n"
        f"📊 Тренд дня: <b>{total_pct:+.2f}%</b>\n"
        f"🔄 Сделок: <b>{total_trades}</b>"
    )
    
    send_telegram_package(caption, "\n\n".join(lessons_list), chart_bytes)
    cur.close(); conn.close()

if __name__ == "__main__":
    generate_report()
