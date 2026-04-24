import psycopg2
import json
import os
import sys
from datetime import datetime, timedelta
from contextlib import closing
from gemini_cli_runner import call_ai_json_with_fallback, call_ai_markdown_with_fallback

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def get_troubled_samples(trader_name, limit=5):
    """Находит в логах моменты, где трейдер получил отказ или сомневался."""
    samples = []
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                # Берем логи, где было много отказов риска или низкий confidence (если есть)
                cur.execute("""
                    SELECT prompt_text, response_text, created_at
                    FROM trading.ai_io_debug_log
                    WHERE trader_name = %s 
                      AND (response_text ILIKE '%risk%' OR response_text ILIKE '%confidence": 0%')
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (trader_name, limit))
                for r in cur.fetchall():
                    samples.append({"prompt": r[0], "response": r[1], "time": r[2].isoformat()})
    except Exception as e:
        print(f"Failed to fetch samples: {e}")
    return samples

def tune_trader_prompt(trader_name):
    print(f"--- Self-Tuning Session for {trader_name} ---")
    samples = get_troubled_samples(trader_name)
    if not samples:
        print(f"No troubled samples found for {trader_name}. Using general performance audit.")
        return

    # 1. Просим ИИ проанализировать ошибки и предложить улучшение промпта
    meta_prompt = f"""
    ROLE: Prompt Engineer & Trading Quant.
    TARGET TRADER: {trader_name}
    FAILING SAMPLES: {json.dumps(samples, ensure_ascii=False)[:8000]}
    
    TASK:
    1. Analyze why the trader was rejected by risk or made suboptimal decisions.
    2. Propose a SPECIFIC addition to his 'Learned Traits' to fix this.
    3. The rule must be concise and algorithmic (e.g., 'If volatility > X, then Y').
    
    RESPOND ONLY IN JSON: {{"analysis": "...", "proposed_trait": "..."}}
    """
    
    # Используем Pro модель для глубокого анализа (10 мин таймаут)
    models = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]
    tuning_data, _ = call_ai_json_with_fallback(meta_prompt, models, name=f"Tuner:{trader_name}", category="tuner")
    
    if tuning_data and tuning_data.get("proposed_trait"):
        new_trait = tuning_data["proposed_trait"]
        print(f"Applying new trait for {trader_name}: {new_trait}")
        
        # 2. Сохраняем в БД (добавляем к существующим чертам)
        try:
            with closing(get_db_connection()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE trading.trader_config
                        SET learned_traits = learned_traits || ' ' || %s,
                            updated_at = NOW()
                        WHERE trader_name = %s
                    """, (new_trait, trader_name))
                conn.commit()
            print(f"Successfully updated DNA for {trader_name}.")
        except Exception as e:
            print(f"Failed to save DNA update: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tune_trader_prompt(sys.argv[1])
    else:
        # Если запущен без аргументов - тюним всю лигу
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT trader_name FROM trading.portfolio")
                traders = [r[0] for r in cur.fetchall()]
        for t in traders:
            tune_trader_prompt(t)
EOF
