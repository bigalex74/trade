#!/usr/bin/env python3
import psycopg2
import json
import subprocess
import os
import argparse
from datetime import datetime, timedelta

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def call_ai_for_backtest(prompt, model="gemini-1.5-flash"):
    cmd = ["gemini", "-p", prompt, "--model", model, "--output-format", "json", "--approval-mode", "yolo"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            raw_out = res.stdout
            if "```json" in raw_out:
                raw_out = raw_out.split("```json")[1].split("```")[0]
            data = json.loads(raw_out)
            resp_text = data.get("response", "")
            if isinstance(resp_text, str) and resp_text.strip().startswith("{"):
                return json.loads(resp_text)
            return data
    except Exception as e:
        print(f"AI Call Error: {e}")
    return None

def run_backtest(trader_name, strategy_desc, start_date, end_date):
    print(f"🚀 Starting Backtest for {trader_name} from {start_date} to {end_date}")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Виртуальный счет
    capital = 10000.0
    positions = {} # {secid: {"qty": 0, "avg_price": 0.0}}
    trades_log = []
    
    # Получаем список торговых дней из БД
    cur.execute("""
        SELECT DISTINCT DATE(period_end) as trading_day 
        FROM analytics.trader_market_windows 
        WHERE window_key = 'current_day' 
          AND period_end >= %s AND period_end <= %s
        ORDER BY trading_day ASC
    """, (start_date, end_date))
    days = [row[0] for row in cur.fetchall()]
    
    if not days:
        print("No historical data found for this period.")
        return

    for current_day in days:
        # 1. Формируем снимок рынка на этот день
        cur.execute("""
            SELECT secid, close, change_pct, indicators 
            FROM analytics.trader_market_windows 
            WHERE window_key = 'current_day' AND DATE(period_end) = %s
        """, (current_day,))
        
        snapshots = {}
        for secid, close, change, indicators in cur.fetchall():
            try:
                inds = indicators if isinstance(indicators, dict) else json.loads(indicators)
            except:
                inds = {}
            snapshots[secid] = {"price": float(close), "change_pct": float(change), "indicators": inds}
            
        if not snapshots: continue
        
        # 2. Подсчет Equity и форматирование позиций для AI
        pos_val = sum([p['qty'] * snapshots.get(sec, {}).get("price", p['avg_price']) for sec, p in positions.items()])
        equity = capital + pos_val
        
        formatted_pos = []
        for sec, p in positions.items():
            curr_price = snapshots.get(sec, {}).get("price", p['avg_price'])
            pnl_pct = ((curr_price / p['avg_price']) - 1) * 100 if p['avg_price'] else 0
            formatted_pos.append({"secid": sec, "qty": p['qty'], "pnl_pct": round(pnl_pct, 2)})
            
        print(f"\n[{current_day}] Equity: {equity:,.2f} ₽ | Positions: {len(positions)}")
            
        # 3. Формируем Промпт
        prompt = f"""
        Act as {trader_name}. Backtesting Mode. Date: {current_day}.
        DNA: {strategy_desc}. 
        Cash: {capital:.2f}. Portfolio: {json.dumps(formatted_pos)}.
        
        MARKET DATA: {json.dumps(snapshots)}
        
        1. Analyze the data. 
        2. Respond ONLY raw JSON object with keys: summary, actions (array with secid, action (buy/sell), reason).
        """
        
        decisions = call_ai_for_backtest(prompt)
        if decisions and "actions" in decisions:
            actions = decisions["actions"]
            for act in actions:
                secid = act.get("secid")
                action_type = str(act.get("action")).lower()
                price = snapshots.get(secid, {}).get("price")
                if not price: continue
                
                # Упрощенное исполнение для бэктеста
                if action_type in ["buy", "add"]:
                    cost = price * 1 # Для бэктеста покупаем по 1 акции
                    if capital >= cost:
                        capital -= cost
                        p = positions.get(secid, {"qty": 0, "avg_price": 0.0})
                        new_qty = p['qty'] + 1
                        new_avg = ((p['qty'] * p['avg_price']) + cost) / new_qty
                        positions[secid] = {"qty": new_qty, "avg_price": new_avg}
                        trades_log.append(f"{current_day}: BUY {secid} @ {price}")
                        print(f"  -> BUY {secid} @ {price}")
                
                elif action_type in ["sell", "close"]:
                    if secid in positions and positions[secid]["qty"] > 0:
                        qty_to_sell = positions[secid]["qty"]
                        income = price * qty_to_sell
                        capital += income
                        del positions[secid]
                        trades_log.append(f"{current_day}: SELL {secid} @ {price}")
                        print(f"  -> SELL {secid} @ {price}")

    # Итоги
    final_pos_val = sum([p['qty'] * snapshots.get(sec, {}).get("price", p['avg_price']) for sec, p in positions.items()])
    final_equity = capital + final_pos_val
    roi = ((final_equity / 10000.0) - 1) * 100
    
    print("\n" + "="*40)
    print(f"🏁 BACKTEST FINISHED FOR {trader_name}")
    print(f"Start Date: {start_date} | End Date: {end_date}")
    print(f"Total Trades: {len(trades_log)}")
    print(f"Final Equity: {final_equity:,.2f} ₽")
    print(f"ROI: {roi:+.2f}%")
    print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM Backtesting Engine")
    parser.add_argument("--name", type=str, required=True, help="Trader Name")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy DNA")
    parser.add_argument("--start", type=str, default="2026-01-01", help="Start Date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2026-04-19", help="End Date YYYY-MM-DD")
    args = parser.parse_args()
    
    run_backtest(args.name, args.strategy, args.start, args.end)
