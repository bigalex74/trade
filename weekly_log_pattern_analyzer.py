import psycopg2
import json
import os
from contextlib import closing
from collections import Counter
from datetime import datetime, timedelta
from gemini_cli_runner import call_ai_markdown_with_fallback

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def analyze_systemic_patterns():
    print("--- Starting Weekly Big Data Pattern Mining ---")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    analysis_results = {
        "timeouts_by_model": Counter(),
        "parse_errors_by_model": Counter(),
        "common_risk_rejections": Counter(),
        "total_calls": 0,
        "failed_calls": 0
    }

    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cur:
                # 1. Анализируем технические сбои
                cur.execute("""
                    SELECT model_id, status, count(*) 
                    FROM trading.ai_call_log 
                    WHERE created_at BETWEEN %s AND %s
                    GROUP BY model_id, status
                """, (start_date, end_date))
                for model, status, count in cur.fetchall():
                    analysis_results["total_calls"] += count
                    if status == "timeout":
                        analysis_results["timeouts_by_model"][model] += count
                        analysis_results["failed_calls"] += count
                    elif status == "parse_error":
                        analysis_results["parse_errors_by_model"][model] += count
                        analysis_results["failed_calls"] += count

                # 2. Анализируем паттерны риск-движка
                cur.execute("""
                    SELECT risk_reasons
                    FROM trading.daily_log_stats
                    WHERE stat_date BETWEEN %s AND %s
                """, (start_date.date(), end_date.date()))
                for r in cur.fetchall():
                    reasons = r[0] if isinstance(r[0], dict) else {}
                    for reason, count in reasons.items():
                        analysis_results["common_risk_rejections"][reason] += count

        # 3. Просим ИИ сделать "Staff Conclusion" на основе этой статистики
        meta_stats = f"""
        WEEKLY STATISTICS ({start_date.date()} to {end_date.date()}):
        - Total AI Calls: {analysis_results['total_calls']}
        - Timeouts: {dict(analysis_results['timeouts_by_model'])}
        - JSON Parse Errors: {dict(analysis_results['parse_errors_by_model'])}
        - Top Risk Rejections: {analysis_results['common_risk_rejections'].most_common(5)}
        """

        prompt = f"""
        ROLE: Principal Site Reliability Engineer & Quant.
        DATA: {meta_stats}
        TASK: Identify top 3 systemic issues in the trading infrastructure or algorithms.
        PROPOSE: 1 technical fix and 1 algorithmic fix.
        """

        report_md, used_model = call_ai_markdown_with_fallback(
            prompt, ["gemini-3.1-pro-preview"], name="SystemicAnalyzer", category="audit"
        )

        if report_md:
            print(f"\n--- SYSTEMIC PATTERN REPORT ({used_model}) ---")
            print(report_md)
            # В реальном сценарии мы бы отправили это в Telegram
            
    except Exception as e:
        print(f"Pattern analysis FAILED: {e}")

if __name__ == "__main__":
    analyze_systemic_patterns()
EOF
