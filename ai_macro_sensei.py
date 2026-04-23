import os
import json
import requests
from datetime import datetime
from algo_kb_client import upload_file_to_algo_kb
from gemini_cli_runner import call_ai_markdown_with_fallback, load_model_rank
from ai_context_cache import is_low_quality_context

# CONFIG
def call_ai(prompt):
    try:
        models = load_model_rank(["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"])
    except:
        models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"]

    return call_ai_markdown_with_fallback(prompt, models, name="MacroSensei", log_func=print, category="general")[0]

def generate_macro_insight():
    print("--- Macro_Sensei 2.0 is analyzing global correlations... ---")
    
    # Промпт для глубокого анализа мировых рынков
    prompt = """
    ROLE: Global Macro Strategist.
    TASK: Analyze current global correlations and their impact on the Moscow Exchange (MOEX).
    
    RESEARCH TOPICS:
    1. US Markets (S&P 500, NASDAQ) & VIX Index (Fear Gauge).
    2. Global Commodities (BRENT, GOLD, GAS).
    3. Crypto Sentiment (BTC/USD) as a risk-on/risk-off indicator.
    4. Geopolitical updates affecting Russian energy/finance.
    
    OBJECTIVES:
    - Identify 'Inter-market Correlations' (e.g., 'S&P 500 drop is leading to capital flight from emerging markets').
    - Assign a 'GLOBAL RISK LEVEL' (Green, Yellow, Orange, Red).
    - Provide 2 specific 'Storm Warnings' if high volatility is expected.
    
    FORMAT: 
    # GLOBAL MACRO SENSEI: [Date]
    ## 🌍 Global Regime: [RISK LEVEL]
    ## 🔍 Market Correlations
    ## 🇷🇺 Impact on MOEX
    ## ⚠️ STORM WARNINGS (Actionable items for traders)
    """
    
    report_md = call_ai(prompt)
    if report_md and not is_low_quality_context(report_md):
        filename = f"macro_global_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md"
        with open(filename, "w") as f: f.write(report_md)
        
        # Сгружаем в базу знаний ALGO (9624)
        upload_file_to_algo_kb(filename, log_func=print)
        
        # Отправляем краткое уведомление в ТГ
        risk_level = "Undefined"
        if "Red" in report_md: risk_level = "🔴 RED (Extreme Risk)"
        elif "Orange" in report_md: risk_level = "🟠 ORANGE (High Volatility)"
        elif "Yellow" in report_md: risk_level = "🟡 YELLOW (Neutral/Mixed)"
        else: risk_level = "🟢 GREEN (Stable/Bullish)"
        
        url_tg = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
        msg = f"🌍 <b>GLOBAL MACRO UPDATE</b>\nRegime: <b>{risk_level}</b>\nGlobal context synced to ALGO KB."
        requests.post(url_tg, json={"chat_id": "923741104", "text": msg, "parse_mode": "HTML"}, 
                      proxies={"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}, timeout=10)
        
        print(f"Macro 2.0 generated and risk alert sent.")
        return True
    return False

if __name__ == "__main__":
    generate_macro_insight()
