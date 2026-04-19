import os
import telebot
import requests
import json
import time
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TMA-Polling-Raw")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
N8N_WEBHOOK = "http://127.0.0.1:5678/webhook/trigger-translation"
PROXY = {"https": "http://127.0.0.1:10808"}
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
MY_CHAT_ID = 923741104

def run_polling():
    telebot.apihelper.proxy = {'https': PROXY['https']}
    bot = telebot.TeleBot(BOT_TOKEN)
    logger.info("Raw polling bot started...")
    
    try:
        bot.send_message(MY_CHAT_ID, "TEST_AUTO_SEND")
    except: pass

    offset = 0
    while True:
        try:
            url = f"{BASE_URL}/getUpdates?offset={offset}&timeout=60"
            resp = requests.get(url, proxies=PROXY, timeout=70)
            data = resp.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if message:
                        logger.info(f"Forwarding msg ID: {message.get('message_id')}")
                        requests.post(N8N_WEBHOOK, json={"message": message}, timeout=15)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)

def start_bot():
    threading.Thread(target=run_polling, daemon=True).start()
