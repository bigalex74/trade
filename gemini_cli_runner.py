import json
import os
import subprocess
import time
import fcntl
from datetime import datetime
from zoneinfo import ZoneInfo

import ai_cost_guard

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.path.expanduser("~")

GEMINI_TRADER_HOME = os.getenv("GEMINI_TRADER_HOME", os.path.join(HOME_DIR, "gemini-trader-home"))
GEMINI_WORKDIR = os.getenv("GEMINI_WORKDIR", os.path.join(HOME_DIR, "gemini-trader-workdir"))
DEFAULT_GEMINI_BIN = os.path.join(HOME_DIR, ".nvm/versions/node/v24.14.0/bin/gemini")
GEMINI_BIN = os.getenv("GEMINI_BIN", DEFAULT_GEMINI_BIN)
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "200"))
GEMINI_CONCURRENCY = int(os.getenv("GEMINI_CONCURRENCY", "2"))
GEMINI_LOCK_WAIT_SECONDS = int(os.getenv("GEMINI_LOCK_WAIT_SECONDS", "240"))
GEMINI_LOCK_DIR = os.getenv("GEMINI_LOCK_DIR", "/tmp")
GEMINI_LOCK_PREFIX = os.getenv("GEMINI_LOCK_PREFIX", "gemini_trader_slot")
TZ = ZoneInfo(os.getenv("AI_JOB_TZ", "Europe/Moscow"))

def _gemini_env():
    env = os.environ.copy()
    env["GEMINI_TRADER_HOME"] = GEMINI_TRADER_HOME
    return env

def acquire_gemini_slot():
    start_time = time.time()
    while time.time() - start_time < GEMINI_LOCK_WAIT_SECONDS:
        for slot in range(GEMINI_CONCURRENCY):
            lock_path = os.path.join(GEMINI_LOCK_DIR, f"{GEMINI_LOCK_PREFIX}_{slot}.lock")
            try:
                f = open(lock_path, "w")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return slot, f
            except (IOError, OSError):
                continue
        time.sleep(1)
    return None, None

def _strip_code_fence(text):
    if not text: return ""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        return "\n".join(lines).strip()
    return text.strip("` \n")

def parse_json_response(stdout):
    raw_text = (stdout or "").strip()
    if not raw_text: raise ValueError("Empty AI response")
    first_brace = raw_text.find('{'); last_brace = raw_text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = raw_text[first_brace:last_brace + 1]
        try: return json.loads(json_str)
        except json.JSONDecodeError:
            json_str = _strip_code_fence(json_str)
            return json.loads(json_str)
    return json.loads(raw_text)

def call_gemini_with_fallback(
    prompt,
    models=None,
    output_format="json",
    name=None,
    log_func=None,
    include_ollama=True,
    category="general",
    trader_name=None,
    response_schema=None,
):
    if models is None:
        models = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro"]

    for fallback_index, model_id in enumerate(models):
        reason = ai_cost_guard.model_unhealthy_reason(model_id, category)
        if reason:
            if log_func: log_func(f"[{name or 'AI'}] Model {model_id} skipped: {reason}.")
            continue

        cmd = [GEMINI_BIN, "--model", model_id, "--prompt", prompt]
        # Мы удалили --json и --format, так как текущая версия бинарника их не поддерживает.
        # Полагаемся на структурированный промпт и наш умный parse_json_response.

        slot, lock_handle = acquire_gemini_slot()
        if slot is None:
            if log_func: log_func(f"[{name or 'AI'}] Failed to acquire Gemini slot.")
            return None, None

        with ai_cost_guard.timer() as elapsed:
            try:
                attempt_timeout = int(os.getenv(f"GEMINI_ATTEMPT_TIMEOUT_SECONDS_{category.upper()}", str(GEMINI_TIMEOUT_SECONDS)))
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=attempt_timeout, env=_gemini_env(), cwd=GEMINI_WORKDIR)
                
                success = (res.returncode == 0)
                if not success:
                    status = "error"
                    err_msg = res.stderr
                else:
                    status = "success"
                    err_msg = None
                    if output_format == "json":
                        try:
                            try: data = parse_json_response(res.stdout)
                            except Exception:
                                if log_func: log_func(f"[{name or 'AI'}] Model {model_id} JSON error, retrying once...")
                                res = subprocess.run(cmd, capture_output=True, text=True, timeout=attempt_timeout, env=_gemini_env(), cwd=GEMINI_WORKDIR)
                                data = parse_json_response(res.stdout)
                            return_data = data
                        except Exception as exc:
                            status = "parse_error"
                            err_msg = str(exc)
                            success = False
                    else:
                        return_data = res.stdout
            except subprocess.TimeoutExpired:
                success = False
                status = "timeout"
                err_msg = f"timeout after {attempt_timeout}s"
            except Exception as exc:
                success = False
                status = "error"
                err_msg = str(exc)
            finally:
                # ОБЯЗАТЕЛЬНО освобождаем слот и закрываем дескриптор
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
                lock_handle.close()

        # Логируем ПОСЛЕ выхода из контекста timer, когда duration уже рассчитан
        ai_cost_guard.log_call(
            category=category, 
            call_name=name, 
            trader_name=trader_name, 
            model_id=model_id, 
            prompt=prompt, 
            response=res.stdout if 'res' in locals() else "", 
            duration_seconds=elapsed.duration, 
            status=status, 
            error=err_msg, 
            fallback_index=fallback_index
        )
        
        if success:
            return return_data, model_id
        else:
            if log_func and status != "model_skipped":
                log_func(f"[{name or 'AI'}] Model {model_id} {status}: {err_msg}")
            continue

    return None, None

def call_ai_json_with_fallback(prompt, models=None, name=None, log_func=None, include_ollama=True, category="general", trader_name=None, response_schema=None):
    return call_gemini_with_fallback(prompt, models=models, output_format="json", name=name, log_func=log_func, include_ollama=include_ollama, category=category, trader_name=trader_name, response_schema=response_schema)

def call_ai_markdown_with_fallback(prompt, models=None, name=None, log_func=None, include_ollama=False, category="general", trader_name=None):
    return call_gemini_with_fallback(prompt, models=models, output_format="text", name=name, log_func=log_func, include_ollama=include_ollama, category=category, trader_name=trader_name)
