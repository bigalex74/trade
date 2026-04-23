import pandas as pd
import psycopg2
import os
import warnings
from datetime import datetime
from algo_kb_client import insert_text_to_algo_kb

warnings.filterwarnings('ignore', category=UserWarning)

DB_CONFIG = {
    "host": "localhost",
    "database": "trading_core",
    "user": "n8n_user",
    "password": "n8n_db_password"
}

OUTPUT_FILE = "/home/user/lightrag-algo/inputs/algo_signals.txt"

def get_data(ticker, interval='1D'):
    conn = psycopg2.connect(**DB_CONFIG)
    query = f"""
        SELECT timestamp, close FROM market_data m
        JOIN assets a ON m.asset_id = a.id
        WHERE a.ticker = '{ticker}' AND m.interval = '{interval}'
        ORDER BY timestamp ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def main():
    # 1. Получаем макро-данные
    oil_df = get_data('BRENT')
    usd_df = get_data('USD000UTSTOM')
    
    macro_context = "### МАКРО-КОНТЕКСТ РЫНКА ###\n"
    if not oil_df.empty:
        macro_context += f"Нефть Brent: {oil_df.iloc[-1]['close']} (Динамика: {round(((oil_df.iloc[-1]['close']/oil_df.iloc[-2]['close'])-1)*100, 2)}%)\n"
    if not usd_df.empty:
        macro_context += f"Курс USD/RUB: {usd_df.iloc[-1]['close']}\n"
    macro_context += "----------------------------\n\n"

    # 2. Анализируем акции
    tickers = ["SBER", "GAZP", "LKOH", "ROSN", "YNDX"]
    report = "ОТЧЕТ РОБОТА-АНАЛИТИКА (Smart Analytics v2)\n\n"
    report += macro_context
    
    for t in tickers:
        df = get_data(t)
        if df.empty: continue
        
        price = df.iloc[-1]['close']
        prev_price = df.iloc[-2]['close']
        change = round(((price/prev_price)-1)*100, 2)
        
        # Простая логика корреляции для Лукойла и Роснефти
        comment = ""
        if t in ["LKOH", "ROSN"] and not oil_df.empty:
            oil_change = (oil_df.iloc[-1]['close']/oil_df.iloc[-2]['close'])-1
            if oil_change > 0.01 and change < 0:
                comment = " (!Аномалия: Нефть растет, а акция падает - возможна точка входа)"
        
        report += f"[{t}] Цена: {price} ({change}%). {comment}\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print("Market analysis with macro context saved.")
    insert_text_to_algo_kb(
        report,
        file_source=f"algo_signals_{datetime.now().strftime('%Y-%m-%d_%H%M')}.txt",
        log_func=print,
    )

if __name__ == "__main__":
    main()
