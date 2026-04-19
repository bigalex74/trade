#!/usr/bin/env python3
import psycopg2
import json
import subprocess
import os

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def call_ai(prompt):
    cmd = ["gemini", "-p", prompt, "--model", "gemini-3.1-pro-preview", "--output-format", "json", "--approval-mode", "yolo"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode == 0:
            raw_out = res.stdout
            if "```json" in raw_out:
                raw_out = raw_out.split("```json")[1].split("```")[0]
            data = json.loads(raw_out)
            resp = data.get("response", "")
            if isinstance(resp, str) and resp.startswith("{"): return json.loads(resp)
            return data
    except Exception as e:
        print(f"Error: {e}")
    return None

def breed_new_agent():
    print("🧬 Starting Genetic Incubator...")
    conn = get_db_connection(); cur = conn.cursor()
    
    cur.execute("SELECT trader_name, cash_balance FROM trading.portfolio")
    portfolios = {row[0]: float(row[1]) for row in cur.fetchall()}
    
    # Считаем Equity
    stats = []
    for name, cash in portfolios.items():
        cur.execute("SELECT SUM(quantity * avg_entry_price) FROM trading.position WHERE trader_name = %s", (name,))
        pos_val = float(cur.fetchone()[0] or 0)
        equity = cash + pos_val
        stats.append({"name": name, "equity": equity})
        
    stats = sorted(stats, key=lambda x: x['equity'], reverse=True)
    best = stats[0]
    worst = stats[-1]
    
    print(f"🏆 Top Performer: {best['name']} ({best['equity']:.2f})")
    print(f"💀 Worst Performer: {worst['name']} ({worst['equity']:.2f})")
    
    # Получаем логику лучшего для мутации
    cur.execute("SELECT learned_traits FROM trading.trader_config WHERE trader_name = %s", (best['name'],))
    best_traits = cur.fetchone()[0]
    
    prompt = f"""
    Act as a Quantitative Hedge Fund Architect. 
    We run a league of 10 AI agents. Our WORST agent ({worst['name']}) is being fired.
    Our BEST agent ({best['name']}) is winning with these traits: {best_traits}.
    
    TASK: Design a completely NEW trading agent to replace the worst one.
    It should be an evolution or a complementary strategy to the best agent (e.g., if the best is Trend Following, maybe create a Volatility Breakout or Mean Reversion bot).
    
    Provide ONLY raw JSON:
    {{
        "new_name": "String (e.g. Volatility_Vlad)",
        "strategy_dna": "String describing exact technical strategy, indicators to use, and mindset",
        "search_query": "String for RAG knowledge base search"
    }}
    """
    
    new_agent = call_ai(prompt)
    if new_agent:
        print("\n🎉 NEW AGENT BORN:")
        print(json.dumps(new_agent, indent=2, ensure_ascii=False))
        print("\nTo integrate, add this to TRADERS_DATA in ai_paper_trader.py:")
        print(f'"{new_agent["new_name"]}": {{"strategy": "{new_agent["strategy_dna"]}", "query": "{new_agent["search_query"]}"}}')
    else:
        print("Incubation failed.")
        
    cur.close(); conn.close()

if __name__ == "__main__":
    breed_new_agent()
