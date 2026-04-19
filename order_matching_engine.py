#!/usr/bin/env python3
import psycopg2
import os
import sys
from datetime import datetime

# CONFIG
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

LOG_FILE = "/home/user/logs/order_matching_engine.log"

def log_event(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def match_orders():
    log_event("Starting Matching Engine cycle...")
    conn = get_db_connection(); cur = conn.cursor()
    
    # 1. Получаем актуальные рыночные цены (из вьюхи)
    cur.execute("SELECT secid, current_price FROM analytics.trader_market_context_v WHERE current_price IS NOT NULL")
    prices = {row[0]: float(row[1]) for row in cur.fetchall()}
    
    # 2. Получаем все ожидающие (PENDING) заявки
    cur.execute("SELECT id, trader_name, secid, order_type, quantity, target_price, model_id FROM trading.orders WHERE status = 'PENDING' FOR UPDATE")
    orders = cur.fetchall()
    
    filled_count = 0
    for order_id, trader_name, secid, order_type, qty, target_price, model_id in orders:
        target_price = float(target_price)
        current_price = prices.get(secid)
        if not current_price: continue
        
        should_fill = False
        execution_price = target_price
        
        # ЛОГИКА МАТЧИНГА (Сведение заявок)
        if order_type == 'limit_buy' and current_price <= target_price:
            should_fill = True
            execution_price = target_price # Исполняем по лимиту или лучше (здесь берем лимит для консерватизма)
        elif order_type == 'limit_sell' and current_price >= target_price:
            should_fill = True
            execution_price = target_price
        elif order_type == 'stop_loss' and current_price <= target_price: # Предполагаем длинную позицию
            should_fill = True
            execution_price = current_price # Стоп исполняется по рынку (проскальзывание)
        
        if should_fill:
            # Исполняем заявку
            cost_or_income = execution_price * qty
            
            if order_type in ['limit_buy']:
                # Обновляем портфель (уменьшаем кеш)
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (cost_or_income, trader_name))
                
                # Обновляем/Вставляем позицию (усреднение цены)
                cur.execute("SELECT quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
                pos_row = cur.fetchone()
                
                curr_qty, curr_avg = (pos_row[0], float(pos_row[1])) if pos_row else (0, 0.0)
                new_qty = curr_qty + qty
                new_avg = ((curr_qty * curr_avg) + cost_or_income) / new_qty
                
                cur.execute("""
                    INSERT INTO trading.position (trader_name, secid, quantity, avg_entry_price, updated_at) 
                    VALUES (%s,%s,%s,%s,NOW()) 
                    ON CONFLICT (trader_name, secid) DO UPDATE SET 
                    quantity=EXCLUDED.quantity, avg_entry_price=EXCLUDED.avg_entry_price, updated_at=NOW()
                """, (trader_name, secid, new_qty, new_avg))
                
                action_str = "BUY"
                
            elif order_type in ['limit_sell', 'stop_loss']:
                # Увеличиваем кеш
                cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (cost_or_income, trader_name))
                
                # Уменьшаем позицию
                cur.execute("UPDATE trading.position SET quantity = quantity - %s WHERE trader_name = %s AND secid = %s", (qty, trader_name, secid))
                cur.execute("DELETE FROM trading.position WHERE quantity <= 0 AND trader_name = %s AND secid = %s", (trader_name, secid))
                
                action_str = "SELL"
                
            # Записываем в журнал и меняем статус заявки
            cur.execute("""
                INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, created_at) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (trader_name, secid, action_str, qty, execution_price, f"FILLED ORDER {order_id} ({order_type})", model_id))
            
            cur.execute("UPDATE trading.orders SET status = 'FILLED', filled_at = NOW() WHERE id = %s", (order_id,))
            log_event(f"[{trader_name}] FILLED ORDER {order_id}: {order_type} {secid} x{qty} @{execution_price}")
            filled_count += 1
            
    conn.commit(); cur.close(); conn.close()
    if filled_count > 0:
        log_event(f"Matching Engine cycle complete. Filled {filled_count} orders.")

if __name__ == "__main__":
    match_orders()
