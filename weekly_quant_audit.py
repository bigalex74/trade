import psycopg2
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from contextlib import closing

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "923741104"
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, proxies=PROXIES, timeout=20)
    except: pass

def calculate_weekly_metrics():
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    print(f"Starting Weekly Quant Audit for period {start_date} to {end_date}...")
    
    report_data = {
        "period_start": str(start_date),
        "period_end": str(end_date),
        "traders": {}
    }
    
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                # 1. Получаем список трейдеров
                cur.execute("SELECT trader_name FROM trading.portfolio")
                traders = [r[0] for r in cur.fetchall()]
                
                for trader in traders:
                    # 2. Получаем статистику по дням за неделю
                    cur.execute("""
                        SELECT stat_date, total_value, cash_balance, positions_value
                        FROM trading.daily_stats
                        WHERE trader_name = %s AND stat_date BETWEEN %s AND %s
                        ORDER BY stat_date ASC
                    """, (trader, start_date, end_date))
                    rows = cur.fetchall()
                    
                    if not rows:
                        continue
                        
                    initial_val = float(rows[0][1])
                    final_val = float(rows[-1][1])
                    profit_abs = final_val - initial_val
                    profit_pct = (profit_abs / initial_val * 100) if initial_val != 0 else 0
                    
                    # Расчет просадки за неделю
                    values = [float(r[1]) for r in rows]
                    peak = values[0]
                    max_dd = 0
                    for v in values:
                        if v > peak: peak = v
                        dd = (peak - v) / peak * 100 if peak > 0 else 0
                        if dd > max_dd: max_dd = dd
                    
                    report_data["traders"][trader] = {
                        "profit_pct": round(profit_pct, 2),
                        "profit_abs": round(profit_abs, 2),
                        "max_drawdown": round(max_dd, 2),
                        "days_active": len(rows)
                    }

            # 3. Сохранение в БД
            report_text = _format_weekly_report(report_data)
            cur.execute("""
                INSERT INTO trading.periodic_audits 
                (audit_type, period_start, period_end, trader_performance, report_text)
                VALUES ('WEEKLY', %s, %s, %s, %s)
                ON CONFLICT (audit_type, period_end) DO UPDATE SET
                    trader_performance = EXCLUDED.trader_performance,
                    report_text = EXCLUDED.report_text
            """, (start_date, end_date, json.dumps(report_data["traders"]), report_text))
            conn.commit()
            
            send_telegram(report_text)
            print("Weekly audit completed and reported.")

    except Exception as e:
        print(f"Weekly audit FAILED: {e}")

def _format_weekly_report(data):
    lines = [
        f"📊 <b>КВАНТОВЫЙ АУДИТ НЕДЕЛИ</b>",
        f"Период: {data['period_start']} — {data['period_end']}",
        f"━━━━━━━━━━━━━━━━━━"
    ]
    
    # Сортируем трейдеров по доходности
    sorted_traders = sorted(data["traders"].items(), key=lambda x: x[1]["profit_pct"], reverse=True)
    
    for name, stats in sorted_traders:
        icon = "🟢" if stats["profit_pct"] >= 0 else "🔴"
        lines.append(
            f"{icon} <b>{name}</b>: <b>{stats['profit_pct']:+.2f}%</b> ({stats['profit_abs']:,} ₽)\n"
            f"   Макс. просадка: {stats['max_drawdown']:.2f}% | Дней: {stats['days_active']}"
        )
        
    return "\n\n".join(lines)

if __name__ == "__main__":
    calculate_weekly_metrics()
