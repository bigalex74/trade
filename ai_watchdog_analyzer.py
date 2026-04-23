import os
import re
import json
import requests
from datetime import datetime
from algo_kb_client import upload_file_to_general_kb
from gemini_cli_runner import call_ai_markdown_with_fallback
from ai_context_cache import is_low_quality_context

# CONFIG
LOG_DIR = "/home/user/logs"

def send_telegram_status(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": "923741104", "text": message, "parse_mode": "HTML"}
    try:
        proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
        requests.post(url, json=payload, proxies=proxies, timeout=10)
    except: pass

def get_log_files():
    logs = []
    for root, dirs, files in os.walk(LOG_DIR):
        for file in files:
            if file.endswith(".log") or file.endswith(".txt"):
                logs.append(os.path.join(root, file))
    return logs

def analyze_logs():
    print("--- STARTING TECHNICAL LOG AUDIT ---")
    test_mode = os.getenv("AI_TEST_MODE", "0") == "1"
    technical_summary = {}
    if test_mode:
        technical_summary = {
            "smoke.log": {
                "errors_count": 1,
                "timeouts": 0,
                "quotas": 0,
                "success": 3,
                "error_types": ["sample recoverable error"],
            }
        }
    else:
        for log_path in get_log_files():
            filename = os.path.basename(log_path)
            try:
                with open(log_path, 'r', errors='ignore') as f:
                    lines = f.readlines()[-1000:]
                content = "".join(lines)
                error_samples = set(re.findall(r"(?:Traceback|Error|Exception|failed): (.*)", content))
                technical_summary[filename] = {
                    "errors_count": len(re.findall(r"Traceback|Error|Exception|failed", content, re.IGNORECASE)),
                    "timeouts": len(re.findall(r"timeout|timed out", content, re.IGNORECASE)),
                    "quotas": len(re.findall(r"429|quota|capacity", content, re.IGNORECASE)),
                    "success": len(re.findall(r"EXECUTED|Tick:", content)),
                    "error_types": list(error_samples)[:5]
                }
            except: continue

    prompt = f"Analyze these logs as an SRE engineer. Suggest technical fixes. Data: {json.dumps(technical_summary)}"
    
    models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    report_md = "Audit failed."
    report_md = call_ai_markdown_with_fallback(prompt, models, name="WatchdogAnalyzer", log_func=print, category="watchdog")[0] or report_md

    try:
        if test_mode:
            print("AI_TEST_MODE=1: skipped KB upload and Telegram notification.")
        else:
            if is_low_quality_context(report_md):
                print("WatchdogAnalyzer produced no usable report; skipped KB upload.")
                return
            filename = f"tech_audit_{datetime.now().strftime('%Y-%m-%d')}.md"
            with open(filename, "w") as f: f.write(report_md)
            upload_file_to_general_kb(filename, log_func=print)
            send_telegram_status(f"🛠 <b>ТЕХНИЧЕСКИЙ АУДИТ ЗАВЕРШЕН</b>\nОтчет о состоянии системы за {datetime.now().strftime('%Y-%m-%d')} загружен в KB.")
    except Exception as e:
        print(f"Audit failed: {e}")

if __name__ == "__main__":
    analyze_logs()
