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
# Пытаемся найти бинарник gemini в стандартных путях, если переменная не задана
DEFAULT_GEMINI_BIN = os.path.join(HOME_DIR, ".nvm/versions/node/v24.14.0/bin/gemini")
GEMINI_BIN = os.getenv("GEMINI_BIN", DEFAULT_GEMINI_BIN)
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "200"))
GEMINI_CONCURRENCY = int(os.getenv("GEMINI_CONCURRENCY", "2"))
GEMINI_LOCK_WAIT_SECONDS = int(os.getenv("GEMINI_LOCK_WAIT_SECONDS", "240"))
GEMINI_LOCK_DIR = os.getenv("GEMINI_LOCK_DIR", "/tmp")
GEMINI_LOCK_PREFIX = os.getenv("GEMINI_LOCK_PREFIX", "gemini_trader_slot")
GEMINI_POOL = os.getenv("GEMINI_POOL", "general")
MOEX_TZ = ZoneInfo(os.getenv("MOEX_TZ", "Europe/Moscow"))


def load_model_rank(fallback=None, include_ollama=False):
    fallback = fallback or ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-3-flash-preview"]
    try:
        with open(os.path.join(BASE_DIR, "ai_model_rank.json")) as f:
            rank = [m["id"] for m in sorted(json.load(f)["models"], key=lambda x: x["priority"])]
    except Exception:
        rank = list(fallback)
    if include_ollama and "ollama/llama3.2" not in rank:
        rank.append("ollama/llama3.2")
    return rank


def acquire_gemini_slot(name=None):
    os.makedirs(GEMINI_LOCK_DIR, exist_ok=True)
    deadline = time.monotonic() + GEMINI_LOCK_WAIT_SECONDS
    while True:
        for slot in candidate_slots():
            lock_path = os.path.join(GEMINI_LOCK_DIR, f"{GEMINI_LOCK_PREFIX}_{slot}.lock")
            handle = open(lock_path, "w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                handle.seek(0)
                handle.truncate()
                handle.write(f"{name or 'AI'} pid={os.getpid()} at={datetime.now().isoformat()}\n")
                handle.flush()
                return slot, handle
            except BlockingIOError:
                handle.close()
        if time.monotonic() >= deadline:
            return None, None
        time.sleep(1)


def is_moex_session(now=None):
    now = now or datetime.now(MOEX_TZ)
    if now.weekday() > 4:
        return False
    if now.hour < 10:
        return False
    if now.hour > 23:
        return False
    if now.hour == 23 and now.minute >= 50:
        return False
    return True


def candidate_slots():
    total = max(1, GEMINI_CONCURRENCY)
    all_slots = list(range(total))
    if total < 2 or not is_moex_session():
        return all_slots
    pool = GEMINI_POOL.lower()
    if pool == "moex":
        return all_slots
    return all_slots[1:]


def is_capacity_error(stdout, stderr):
    output = ((stdout or "") + "\n" + (stderr or "")).lower()
    return any(token in output for token in ["capacity", "overloaded", "quota", "exhausted", "429"])


def brief_output(stdout, stderr, limit=300):
    return ((stderr or "") + "\n" + (stdout or "")).strip().replace("\n", " ")[:limit]


def attempt_timeout_seconds(category: str) -> int:
    category_key = f"GEMINI_ATTEMPT_TIMEOUT_SECONDS_{category.upper()}"
    return max(1, int(os.getenv(category_key, os.getenv("GEMINI_ATTEMPT_TIMEOUT_SECONDS", str(GEMINI_TIMEOUT_SECONDS)))))


def _gemini_env():
    env = os.environ.copy()
    env["HOME"] = GEMINI_TRADER_HOME
    env["PATH"] = f"{os.path.dirname(GEMINI_BIN)}:{env.get('PATH', '')}"
    return env


def _strip_code_fence(text):
    text = (text or "").strip()
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    if text.startswith("json"):
        return text[4:].strip()
    return text.strip("` \n")


def parse_json_response(stdout):
    raw_text = (stdout or "").strip()
    if not raw_text:
        raise ValueError("Empty AI response")
        
    # Пытаемся найти границы JSON объекта { ... }
    first_brace = raw_text.find('{')
    last_brace = raw_text.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = raw_text[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Если прямой парсинг не удался, пробуем очистить от markdown и повторить
            json_str = _strip_code_fence(json_str)
            return json.loads(json_str)
            
    # Если скобки не найдены, пробуем распарсить как есть (возможно это прямой JSON список или примитив)
    return json.loads(raw_text)


def call_gemini_with_fallback(
    prompt,
    models=None,
    output_format="json",
    name=None,
    log_func=None,
    include_ollama=False,
    category=None,
    trader_name=None,
):
    category = category or ai_cost_guard.infer_category(name)
    decision = ai_cost_guard.preflight(prompt, category, call_name=name, trader_name=trader_name)
    if not decision.allowed:
        if log_func:
            log_func(f"[{name or 'AI'}] AI budget blocked: {decision.reason}.")
        return None, None

    rank = list(models or load_model_rank(include_ollama=include_ollama))
    if include_ollama and "ollama/llama3.2" not in rank:
        rank.append("ollama/llama3.2")
    max_attempts = max(1, 1 + ai_cost_guard.max_fallbacks(category))
    attempts = 0

    slot, lock_handle = acquire_gemini_slot(name)
    if lock_handle is None:
        if log_func:
            log_func(f"[{name or 'AI'}] No Gemini slot available within {GEMINI_LOCK_WAIT_SECONDS}s.")
        return None, None

    started = time.monotonic()
    try:
        for fallback_index, model_id in enumerate(rank):
            if attempts >= max_attempts:
                if log_func:
                    log_func(f"[{name or 'AI'}] Fallback budget reached: attempts={attempts}, max={max_attempts}.")
                break
            unhealthy_reason = ai_cost_guard.model_unhealthy_reason(model_id, category)
            if unhealthy_reason:
                ai_cost_guard.log_model_skipped(
                    category=category,
                    call_name=name,
                    trader_name=trader_name,
                    model_id=model_id,
                    prompt=prompt,
                    reason=unhealthy_reason,
                    fallback_index=fallback_index,
                )
                if log_func:
                    log_func(f"[{name or 'AI'}] Model {model_id} skipped by health guard: {unhealthy_reason}.")
                continue

            remaining_total = max(1, int(GEMINI_TIMEOUT_SECONDS - (time.monotonic() - started)))
            if remaining_total <= 1:
                if log_func:
                    log_func(f"[{name or 'AI'}] AI timeout after {GEMINI_TIMEOUT_SECONDS}s.")
                break
            attempt_timeout = min(remaining_total, attempt_timeout_seconds(category))

            if model_id.startswith("ollama/"):
                attempts += 1
                try:
                    with ai_cost_guard.timer() as elapsed:
                        res = subprocess.run(
                            ["ollama", "run", model_id.replace("ollama/", ""), prompt],
                            capture_output=True,
                            text=True,
                            timeout=attempt_timeout,
                        )
                    if res.returncode == 0 and "{" in res.stdout:
                        raw = res.stdout[res.stdout.find("{"):res.stdout.rfind("}") + 1]
                        data = json.loads(raw)
                        ai_cost_guard.log_call(
                            category=category,
                            call_name=name,
                            trader_name=trader_name,
                            model_id=model_id,
                            prompt=prompt,
                            response=res.stdout,
                            duration_seconds=elapsed.duration,
                            status="success",
                            fallback_index=fallback_index,
                        )
                        return data, model_id
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response=res.stdout,
                        duration_seconds=elapsed.duration,
                        status="error",
                        error_class="nonzero_or_empty_json",
                        error=brief_output(res.stdout, res.stderr),
                        fallback_index=fallback_index,
                    )
                except subprocess.TimeoutExpired:
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response="",
                        duration_seconds=attempt_timeout,
                        status="timeout",
                        error_class="timeout",
                        error=f"timeout after {attempt_timeout}s",
                        fallback_index=fallback_index,
                    )
                    if log_func:
                        log_func(f"[{name or 'AI'}] Model {model_id} timed out.")
                    continue
                except Exception as exc:
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response="",
                        duration_seconds=None,
                        status="parse_error",
                        error_class=type(exc).__name__,
                        error=str(exc),
                        fallback_index=fallback_index,
                    )
                    if log_func:
                        log_func(f"[{name or 'AI'}] Model {model_id} error: {type(exc).__name__}: {exc}")
                    continue
                continue

            cmd = [
                GEMINI_BIN,
                "-p",
                prompt,
                "--model",
                model_id,
                "--output-format",
                output_format,
                "--approval-mode",
                "default",
                "--allowed-mcp-server-names",
                "__none__",
            ]
            attempts += 1
            try:
                os.makedirs(GEMINI_WORKDIR, exist_ok=True)
                with ai_cost_guard.timer() as elapsed:
                    res = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=attempt_timeout,
                        env=_gemini_env(),
                        cwd=GEMINI_WORKDIR,
                    )
                if is_capacity_error(res.stdout, res.stderr):
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response=res.stdout,
                        duration_seconds=elapsed.duration,
                        status="exhausted",
                        error_class="capacity_or_quota",
                        error=brief_output(res.stdout, res.stderr),
                        fallback_index=fallback_index,
                    )
                    if log_func:
                        log_func(f"[{name or 'AI'}] Model {model_id} exhausted. Trying next...")
                    continue
                if res.returncode != 0:
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response=res.stdout,
                        duration_seconds=elapsed.duration,
                        status="error",
                        error_class=f"exit_{res.returncode}",
                        error=brief_output(res.stdout, res.stderr),
                        fallback_index=fallback_index,
                    )
                    if log_func:
                        log_func(f"[{name or 'AI'}] Model {model_id} exited {res.returncode}: {brief_output(res.stdout, res.stderr)}")
                    continue
                if output_format == "json":
                    try:
                        # Попытка парсинга с возможностью одного локального ретрая при ошибке формата
                        try:
                            data = parse_json_response(res.stdout)
                        except Exception:
                            # Локальный ретрай для этой же модели при ошибке парсинга
                            if log_func:
                                log_func(f"[{name or 'AI'}] Model {model_id} JSON error, retrying once...")
                            res = subprocess.run(
                                cmd,
                                capture_output=True,
                                text=True,
                                timeout=attempt_timeout,
                                env=_gemini_env(),
                                cwd=GEMINI_WORKDIR,
                            )
                            data = parse_json_response(res.stdout)
                    except Exception as exc:
                        ai_cost_guard.log_call(
                            category=category,
                            call_name=name,
                            trader_name=trader_name,
                            model_id=model_id,
                            prompt=prompt,
                            response=res.stdout,
                            duration_seconds=elapsed.duration,
                            status="parse_error",
                            error_class=type(exc).__name__,
                            error=str(exc),
                            fallback_index=fallback_index,
                        )
                        if log_func:
                            log_func(f"[{name or 'AI'}] Model {model_id} JSON parse failed after retry: {type(exc).__name__}")
                        continue
                    ai_cost_guard.log_call(
                        category=category,
                        call_name=name,
                        trader_name=trader_name,
                        model_id=model_id,
                        prompt=prompt,
                        response=res.stdout,
                        duration_seconds=elapsed.duration,
                        status="success",
                        fallback_index=fallback_index,
                    )
                    return data, model_id
                ai_cost_guard.log_call(
                    category=category,
                    call_name=name,
                    trader_name=trader_name,
                    model_id=model_id,
                    prompt=prompt,
                    response=res.stdout,
                    duration_seconds=elapsed.duration,
                    status="success",
                    fallback_index=fallback_index,
                )
                return res.stdout.strip(), model_id
            except subprocess.TimeoutExpired:
                ai_cost_guard.log_call(
                    category=category,
                    call_name=name,
                    trader_name=trader_name,
                    model_id=model_id,
                    prompt=prompt,
                    response="",
                    duration_seconds=attempt_timeout,
                    status="timeout",
                    error_class="timeout",
                    error=f"timeout after {attempt_timeout}s",
                    fallback_index=fallback_index,
                )
                if log_func:
                    log_func(f"[{name or 'AI'}] Model {model_id} timed out.")
                continue
            except Exception as exc:
                ai_cost_guard.log_call(
                    category=category,
                    call_name=name,
                    trader_name=trader_name,
                    model_id=model_id,
                    prompt=prompt,
                    response="",
                    duration_seconds=None,
                    status="error",
                    error_class=type(exc).__name__,
                    error=str(exc),
                    fallback_index=fallback_index,
                )
                if log_func:
                    log_func(f"[{name or 'AI'}] Model {model_id} parse/error: {type(exc).__name__}: {exc}")
                continue
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()
    return None, None


def call_ai_json_with_fallback(prompt, models=None, name=None, log_func=None, include_ollama=False, category=None, trader_name=None):
    return call_gemini_with_fallback(
        prompt,
        models=models,
        output_format="json",
        name=name,
        log_func=log_func,
        include_ollama=include_ollama,
        category=category,
        trader_name=trader_name,
    )


def call_ai_markdown_with_fallback(prompt, models=None, name=None, log_func=None, category=None, trader_name=None):
    return call_gemini_with_fallback(
        prompt,
        models=models,
        output_format="text",
        name=name,
        log_func=log_func,
        include_ollama=False,
        category=category,
        trader_name=trader_name,
    )
