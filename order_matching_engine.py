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

LOG_FILE = "/home/user/logs/traders/matching_engine.log"
SLIPPAGE_PCT = 0.0005  # 0.05% slippage

def log_event(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def get_db_connection(): 
    return psycopg2.connect(**DB_CONFIG)

def match_orders():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        log_event(f"Failed to connect to DB: {e}")
        return

    try:
        # 1. Получаем актуальные рыночные цены
        cur.execute("SELECT secid, current_price FROM analytics.trader_market_context_v WHERE current_price IS NOT NULL")
        prices = {row[0]: float(row[1]) for row in cur.fetchall()}
        
        # 2. Получаем балансы всех трейдеров
        cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio")
        balances = {row[0]: float(row[1]) for row in cur.fetchall()}
        
        # 3. Получаем все ожидающие (PENDING) заявки
        cur.execute("SELECT id, trader_name, secid, order_type, quantity, target_price, model_id FROM trading.orders WHERE status = 'PENDING' FOR UPDATE")
        orders = cur.fetchall()
        
        filled_count = 0
        for order_id, trader_name, secid, order_type, qty, target_price, model_id in orders:
            target_price = float(target_price)
            current_price = prices.get(secid)
            if not current_price: continue
            
            should_fill = False
            execution_price = target_price
            
            # ЛОГИКА МАТЧИНГА (с учетом проскальзывания 0.05%)
            if order_type == 'limit_buy' and current_price <= target_price:
                should_fill = True
                # Покупка: цена исполнения ухудшается проскальзыванием, но ограничена лимитом
                execution_price = min(target_price, current_price * (1 + SLIPPAGE_PCT))
            elif order_type == 'limit_sell' and current_price >= target_price:
                should_fill = True
                # Продажа: цена исполнения ухудшается проскальзыванием, ограничена лимитом
                execution_price = max(target_price, current_price * (1 - SLIPPAGE_PCT))
            elif order_type == 'stop_loss' and current_price <= target_price:
                should_fill = True
                # Стоп: исполняется по рынку с проскальзыванием
                execution_price = current_price * (1 - SLIPPAGE_PCT)
            
            if should_fill:
                cost_or_income = execution_price * qty
                
                # ЗАЩИТА: Проверка маржи/баланса
                if order_type == 'limit_buy':
                    if balances.get(trader_name, 0.0) < cost_or_income:
                        cur.execute("UPDATE trading.orders SET status = 'CANCELLED', filled_at = NOW(), reason = 'INSUFFICIENT_FUNDS' WHERE id = %s", (order_id,))
                        log_event(f"[{trader_name}] CANCELLED ORDER {order_id} (No funds): need {cost_or_income:.2f}, have {balances.get(trader_name, 0.0):.2f}")
                        continue
                    
                    balances[trader_name] -= cost_or_income
                    cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance - %s WHERE trader_name = %s", (cost_or_income, trader_name))
                    
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
                    # ЗАЩИТА: Проверка наличия позиции (защита от "голых" шортов)
                    cur.execute("SELECT quantity FROM trading.position WHERE trader_name = %s AND secid = %s", (trader_name, secid))
                    pos_row = cur.fetchone()
                    curr_qty = pos_row[0] if pos_row else 0
                    
                    if curr_qty < qty:
                        qty = max(0, curr_qty)
                        cost_or_income = execution_price * qty
                        if qty == 0:
                            cur.execute("UPDATE trading.orders SET status = 'CANCELLED', filled_at = NOW(), reason = 'NO_POSITION' WHERE id = %s", (order_id,))
                            continue
                            
                    balances[trader_name] += cost_or_income
                    cur.execute("UPDATE trading.portfolio SET cash_balance = cash_balance + %s WHERE trader_name = %s", (cost_or_income, trader_name))
                    
                    cur.execute("UPDATE trading.position SET quantity = quantity - %s WHERE trader_name = %s AND secid = %s", (qty, trader_name, secid))
                    cur.execute("DELETE FROM trading.position WHERE quantity <= 0 AND trader_name = %s AND secid = %s", (trader_name, secid))
                    
                    action_str = "SELL"
                    
                # Запись в журнал
                cur.execute("""
                    INSERT INTO trading.journal (trader_name, secid, action, quantity, price, reason, model_id, created_at) 
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                """, (trader_name, secid, action_str, qty, execution_price, f"FILLED ORDER {order_id} ({order_type})", model_id))
                
                cur.execute("UPDATE trading.orders SET status = 'FILLED', filled_at = NOW() WHERE id = %s", (order_id,))
                log_event(f"[{trader_name}] FILLED ORDER {order_id}: {order_type} {secid} x{qty} @{execution_price:.4f}")
                filled_count += 1
                
        conn.commit()
        if filled_count > 0:
            log_event(f"Matching Engine cycle complete. Filled {filled_count} orders.")
            
    except Exception as e:
        conn.rollback()
        log_event(f"CRITICAL ERROR in Matching Engine: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    match_orders()
