from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import requests
import httpx
import docx
import shutil
import telegram_polling

app = FastAPI(title="bigalexn8n Apps Hub")
telegram_polling.start_bot()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

N8N_WEBHOOK_URL = "https://bigalexn8n.ru/webhook/trigger-translation"
DB_CONFIG_POSTGRES = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "database": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
    "port": int(os.getenv("DB_PORT", 5432))
}

def get_conn_pg(): return psycopg2.connect(**DB_CONFIG_POSTGRES)

DB_CONFIG_RESEARCH = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "database": "market_research",
    "user": "n8n_user",
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
    "port": int(os.getenv("DB_PORT", 5432))
}

def get_conn_research(): return psycopg2.connect(**DB_CONFIG_RESEARCH)

class StartTranslationRequest(BaseModel):
    file_id: str; file_name: str; chat_id: int = None
    bp_file_id: str = None; bp_file_name: str = None
    pp_file_id: str = None; pp_file_name: str = None
    glossary_id: str = None; glossary_file_name: str = None
    create_glossary: bool = False

# Работа с файлами (с фильтрацией по chat_id)
@app.get("/api/get-form-data")
async def get_form_data(chat_id: int):
    conn = get_conn_pg()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT type, lang, message->'document'->>'file_name' as name, message->'document'->>'file_id' as file_id FROM telegram_messages WHERE (message->'chat'->>'id')::bigint = %s AND message->'document' IS NOT NULL AND (is_translate IS NULL OR is_translate = false) ORDER BY date_time DESC", (chat_id,))
    all_items = cur.fetchall()
    cur.close()
    conn.close()
    return {"files_ko": [f for f in all_items if f['lang'] == 'ko'], "glossaries": [f for f in all_items if f['type'] == 'xlsx'], "prompts_ru": [f for f in all_items if f['lang'] == 'ru']}

@app.post("/api/files/hide")
async def hide_files(data: dict):
    file_ids = data.get("file_ids", []); chat_id = data.get("chat_id")
    conn = get_conn_pg()
    cur = conn.cursor()
    cur.execute("UPDATE telegram_messages SET is_translate = true WHERE message->'document'->>'file_id' = ANY(%s) AND (message->'chat'->>'id')::bigint = %s", (file_ids, chat_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

# Работа с промптами (БЕЗ фильтрации по chat_id)
@app.get("/api/prompts")
async def get_prompts_db():
    conn = get_conn_pg()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, name, prompt FROM translate_prompts ORDER BY name")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

@app.post("/api/prompts")
async def create_prompt(data: dict):
    conn = get_conn_pg()
    cur = conn.cursor()
    cur.execute("INSERT INTO translate_prompts (name, prompt) VALUES (%s, %s)", (data['name'], data['prompt']))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

@app.put("/api/prompts/{prompt_id}")
async def update_prompt(prompt_id: int, data: dict):
    conn = get_conn_pg()
    cur = conn.cursor()
    cur.execute("INSERT INTO translate_prompts_history (prompt_id, name, prompt, version_date) SELECT id, name, prompt, CURRENT_TIMESTAMP FROM translate_prompts WHERE id = %s", (prompt_id,))
    cur.execute("UPDATE translate_prompts SET name = %s, prompt = %s WHERE id = %s", (data['name'], data['prompt'], prompt_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

@app.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int):
    conn = get_conn_pg()
    cur = conn.cursor()
    cur.execute("DELETE FROM translate_prompts WHERE id = %s", (prompt_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

@app.get("/api/prompts/{prompt_id}/history")
async def get_prompt_history(prompt_id: int):
    conn = get_conn_pg()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, prompt_id, name, prompt, version_date FROM translate_prompts_history WHERE prompt_id = %s ORDER BY version_date DESC", (prompt_id,))
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

@app.get("/api/trade/league")
async def get_trade_league(division: str = "moex"):
    try:
        db_name = "market_research" if division == "moex" else "crypto_research"
        config = DB_CONFIG_RESEARCH.copy()
        config["database"] = db_name
        
        conn = psycopg2.connect(**config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT p.trader_name, p.cash_balance, c.learned_traits as memory FROM trading.portfolio p LEFT JOIN trading.trader_config c ON p.trader_name = c.trader_name ORDER BY p.trader_name")
        portfolios = cur.fetchall()
        
        cur.execute("SELECT trader_name, secid, quantity, avg_entry_price FROM trading.position WHERE quantity != 0")
        positions = cur.fetchall()
        
        cur.execute("SELECT trader_name, secid, action, quantity, price, created_at FROM trading.journal ORDER BY created_at DESC LIMIT 10")
        journal = cur.fetchall()
        
        cur.execute("SELECT id, trader_name, secid, order_type, quantity, target_price FROM trading.orders WHERE status = 'PENDING'")
        orders = cur.fetchall()
        
        cur.execute("SELECT secid, score, summary FROM analytics.market_sentiment")
        sentiment = cur.fetchall()

        # 6. Список активных инструментов
        cur.execute("SELECT secid, issuer_name FROM ref.instrument WHERE active = true")
        instruments = cur.fetchall()
        
        cur.close(); conn.close()
        return {
            "division": division,
            "traders": portfolios, 
            "positions": positions, 
            "journal": journal, 
            "orders": orders, 
            "sentiment": sentiment,
            "instruments": instruments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-translation")
async def start_translation(req: StartTranslationRequest):
    async with httpx.AsyncClient() as client:
        await client.post(N8N_WEBHOOK_URL, json=req.dict(), timeout=10.0)
        return {"status": "success"}

@app.post("/api/upload-file")
async def upload_file(file: UploadFile = File(...)):
    try:
        if file.filename.endswith(".docx"):
            with open("temp.docx", "wb") as buffer: shutil.copyfileobj(file.file, buffer)
            doc = docx.Document("temp.docx")
            full_text = "\n".join([para.text for para in doc.paragraphs])
            os.remove("temp.docx")
            return {"text": full_text}
        else:
            content = await file.read()
            return {"text": content.decode("utf-8")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def main_hub():
    with open("static/index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/files", response_class=HTMLResponse)
async def files_page():
    with open("static/files/index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/manage-menu", response_class=HTMLResponse)
async def manage_menu():
    with open("static/manage-menu.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/manage", response_class=HTMLResponse)
async def manage_page():
    with open("static/manage/index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/prompts", response_class=HTMLResponse)
async def prompts_page():
    with open("static/prompts/index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/trade", response_class=HTMLResponse)
async def trade_page():
    with open("static/trade/index.html", "r", encoding="utf-8") as f: return f.read()

app.mount("/static", StaticFiles(directory="static"), name="static")
