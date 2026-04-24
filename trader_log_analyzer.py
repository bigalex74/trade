import json
import os
import sys
from collections import Counter
from datetime import datetime

def analyze_logs(log_file):
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return

    stats = {
        "total_sessions": 0,
        "ai_success": 0,
        "ai_failed": 0,
        "risk_accepted": 0,
        "risk_rejected": 0,
        "trader_stats": {},
        "risk_reasons": Counter(),
        "models_used": Counter()
    }

    try:
        with open(log_file, "r") as f:
            for line in f:
                event = json.loads(line)
                trader = event["trader"]
                etype = event["event"]
                data = event["data"]

                if trader not in stats["trader_stats"]:
                    stats["trader_stats"][trader] = {
                        "sessions": 0, "ai_ok": 0, "ai_fail": 0, 
                        "buy": 0, "sell": 0, "hold": 0,
                        "risk_ok": 0, "risk_err": 0
                    }
                
                tstat = stats["trader_stats"][trader]

                if etype == "ai_response":
                    stats["ai_success"] += 1
                    tstat["ai_ok"] += 1
                    stats["models_used"][data.get("model")] += 1
                    
                    actions = data.get("decision", {}).get("actions", [])
                    if not actions:
                        tstat["hold"] += 1
                    for a in actions:
                        act = a.get("action", "").lower()
                        if "buy" in act: tstat["buy"] += 1
                        elif "sell" in act or "short" in act: tstat["sell"] += 1

                elif etype == "ai_failed":
                    stats["ai_failed"] += 1
                    tstat["ai_fail"] += 1

                elif etype == "risk_review":
                    stats["risk_accepted"] += data.get("accepted", 0)
                    stats["risk_rejected"] += data.get("rejected", 0)
                    tstat["risk_ok"] += data.get("accepted", 0)
                    tstat["risk_err"] += data.get("rejected", 0)
                    
                    reasons = data.get("rejection_reasons", [])
                    for r in reasons:
                        stats["risk_reasons"][r] += 1

        _print_report(stats, log_file)

    except Exception as e:
        print(f"Analysis failed: {e}")

def _print_report(stats, filename):
    print(f"\n{'='*60}")
    print(f"📊 ОТЧЕТ ПО ЛОГАМ ТРЕЙДЕРОВ: {os.path.basename(filename)}")
    print(f"{'='*60}")
    
    total_ai = stats["ai_success"] + stats["ai_failed"]
    ai_sr = (stats["ai_success"] / total_ai * 100) if total_ai > 0 else 0
    
    print(f"\n🔹 ИИ-АНАЛИТИКА (Успешность вызовов: {ai_sr:.1f}%):")
    for model, count in sorted(stats["models_used"].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {model}: {count} успешных ответов")
    print(f"  - Ошибок/Таймаутов: {stats['ai_failed']}")

    print(f"\n🔹 ВОРОНКА РИСК-ДВИЖКА:")
    print(f"  - Одобрено ордеров: {stats['risk_accepted']}")
    print(f"  - Отклонено риском: {stats['risk_rejected']}")
    if stats["risk_reasons"]:
        print(f"  Причины отказов:")
        for reason, count in stats["risk_reasons"].most_common(5):
            print(f"    - {reason}: {count}")

    print(f"\n🔹 СТАТИСТИКА ПО ТРЕЙДЕРАМ:")
    print(f"  {'Трейдер':<20} | {'AI OK':<6} | {'Buy':<5} | {'Sell':<5} | {'Hold':<5} | {'Risk REJ':<8}")
    print(f"  {'-'*65}")
    for t, s in sorted(stats["trader_stats"].items()):
        print(f"  {t:<20} | {s['ai_ok']:<6} | {s['buy']:<5} | {s['sell']:<5} | {s['hold']:<5} | {s['risk_err']:<8}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
    log_path = f"/home/user/logs/analytics/events_{target_date}.jsonl"
    analyze_logs(log_path)
EOF
