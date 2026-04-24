import json
import os
import sys
import requests
import psycopg2
from collections import Counter
from datetime import datetime
from contextlib import closing

# CONFIG
DB_CONFIG = {"host": os.getenv("DB_HOST", "localhost"), "database": "market_research", "user": os.getenv("DB_USER", "n8n_user"), "password": os.getenv("DB_PASSWORD", "n8n_db_password")}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "923741104"
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def send_telegram(message):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, proxies=PROXIES, timeout=15)
    except: pass

def get_radar_anomalies(target_date):
    """Получает все аномалии за день из БД."""
    anomalies = set()
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT secid FROM analytics.market_radar_log WHERE created_at::date = %s", (target_date,))
                anomalies = {r[0] for r in cur.fetchall()}
    except Exception as e:
        print(f"Failed to fetch radar anomalies: {e}")
    return anomalies

def analyze_logs(log_file, target_date, auto_mode=False):
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return

    radar_set = get_radar_anomalies(target_date)
    stats = {
        "ai_success": 0, "ai_failed": 0, "risk_accepted": 0, "risk_rejected": 0,
        "trader_stats": {}, "risk_reasons": Counter(), "models_used": Counter(),
        "ai_chosen_tickers": Counter(), "radar_hits": 0, "radar_misses": 0
    }

    try:
        with open(log_file, "r") as f:
            for line in f:
                event = json.loads(line)
                trader, etype, data = event["trader"], event["event"], event["data"]
                if trader not in stats["trader_stats"]:
                    stats["trader_stats"][trader] = {"ai_ok": 0, "ai_fail": 0, "buy": 0, "sell": 0, "hold": 0, "risk_err": 0}
                tstat = stats["trader_stats"][trader]

                if etype == "ai_response":
                    stats["ai_success"] += 1; tstat["ai_ok"] += 1
                    stats["models_used"][data.get("model")] += 1
                    actions = data.get("decision", {}).get("actions", [])
                    if not actions: tstat["hold"] += 1
                    for a in actions:
                        secid = a.get("secid", "").upper()
                        act = str(a.get("action", "")).lower()
                        if secid:
                            stats["ai_chosen_tickers"][secid] += 1
                            if secid in radar_set: stats["radar_hits"] += 1
                            else: stats["radar_misses"] += 1
                        if "buy" in act: tstat["buy"] += 1
                        elif "sell" in act or "short" in act: tstat["sell"] += 1

                elif etype == "ai_failed":
                    stats["ai_failed"] += 1; tstat["ai_fail"] += 1
                elif etype == "risk_review":
                    stats["risk_accepted"] += data.get("accepted", 0)
                    stats["risk_rejected"] += data.get("rejected", 0)
                    tstat["risk_err"] += data.get("rejected", 0)
                    for r in data.get("rejection_reasons", []): stats["risk_reasons"][r] += 1

        report_text = _format_report(stats, target_date, len(radar_set))
        print(report_text)
        if auto_mode:
            send_telegram(report_text)
            _save_to_db(target_date, stats, report_text)
    except Exception as e: print(f"Analysis failed: {e}")

def _format_report(stats, target_date, radar_total):
    total_ai = stats["ai_success"] + stats["ai_failed"]
    ai_sr = (stats["ai_success"] / total_ai * 100) if total_ai > 0 else 0
    radar_efficiency = (stats["radar_hits"] / (stats["radar_hits"] + stats["radar_misses"]) * 100) if (stats["radar_hits"] + stats["radar_misses"]) > 0 else 0
    
    lines = [
        f"📊 <b>ДЕЙСТВИЯ ТРЕЙДЕРОВ: {target_date}</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"🤖 <b>ИИ-АНАЛИТИКА:</b>",
        f"Успешность: {ai_sr:.1f}% ({stats['ai_success']}/{total_ai})",
        f"Модели: " + ", ".join([f"{m}({c})" for m, c in stats["models_used"].items()]),
        f"\n📡 <b>АУДИТ МАРКЕТ-РАДАРА:</b>",
        f"Найдено аномалий: {radar_total}",
        f"Совпадение с ИИ: {radar_efficiency:.1f}%",
        f"Пропущено радаром: {stats['radar_misses']} действий ИИ",
        f"\n🛡 <b>РИСКИ:</b> Одобрено: {stats['risk_accepted']} | Отк: {stats['risk_rejected']}",
        f"\n👥 <b>ТРЕЙДЕРЫ (OK | B/S/H | REJ):</b>"
    ]
    for t, s in sorted(stats["trader_stats"].items()):
        lines.append(f"<code>{t:<14}</code>: {s['ai_ok']} | {s['buy']}/{s['sell']}/{s['hold']} | {s['risk_err']}")
    return "\n".join(lines)

def _save_to_db(stat_date, stats, report_text):
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trading.daily_log_stats 
                    (stat_date, ai_success_count, ai_failed_count, risk_accepted_count, risk_rejected_count, risk_reasons, trader_breakdown, report_text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stat_date) DO UPDATE SET
                        ai_success_count = EXCLUDED.ai_success_count, ai_failed_count = EXCLUDED.ai_failed_count,
                        risk_accepted_count = EXCLUDED.risk_accepted_count, risk_rejected_count = EXCLUDED.risk_rejected_count,
                        risk_reasons = EXCLUDED.risk_reasons, trader_breakdown = EXCLUDED.trader_breakdown, report_text = EXCLUDED.report_text
                """, (stat_date, stats["ai_success"], stats["ai_failed"], stats["risk_accepted"], stats["risk_rejected"], json.dumps(dict(stats["risk_reasons"])), json.dumps(stats["trader_stats"]), report_text))
            conn.commit()
    except Exception as e: print(f"DB save failed: {e}")

if __name__ == "__main__":
    is_auto = "--auto" in sys.argv
    target_date = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else datetime.now().strftime('%Y-%m-%d')
    log_dir = "/home/user/logs/analytics"
    log_path = os.path.join(log_dir, f"events_{target_date}.jsonl")
    analyze_logs(log_path, target_date, auto_mode=is_auto)
EOF
