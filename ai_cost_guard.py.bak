#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import psycopg2


DB_CONFIG = {
    "host": os.getenv("AI_JOBS_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("AI_JOBS_DB_NAME", os.getenv("DB_NAME", "market_research")),
    "user": os.getenv("AI_JOBS_DB_USER", os.getenv("DB_USER", "n8n_user")),
    "password": os.getenv("AI_JOBS_DB_PASSWORD", os.getenv("DB_PASSWORD", "n8n_db_password")),
}

DDL = """
CREATE TABLE IF NOT EXISTS trading.ai_call_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    script_name TEXT,
    call_name TEXT,
    trader_name TEXT,
    category TEXT NOT NULL,
    model_id TEXT,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    prompt_tokens_est INTEGER NOT NULL DEFAULT 0,
    response_chars INTEGER NOT NULL DEFAULT 0,
    duration_seconds NUMERIC,
    status TEXT NOT NULL,
    error_class TEXT,
    error TEXT,
    fallback_index INTEGER,
    request_allowed BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ai_call_log_created_idx
    ON trading.ai_call_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_call_log_category_created_idx
    ON trading.ai_call_log (category, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_call_log_model_created_idx
    ON trading.ai_call_log (model_id, created_at DESC);
CREATE TABLE IF NOT EXISTS trading.ai_io_debug_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    script_name TEXT,
    call_name TEXT,
    trader_name TEXT,
    category TEXT NOT NULL,
    model_id TEXT,
    status TEXT NOT NULL,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    response_chars INTEGER NOT NULL DEFAULT 0,
    prompt_text TEXT,
    response_text TEXT,
    truncated BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ai_io_debug_log_created_idx
    ON trading.ai_io_debug_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_io_debug_log_call_created_idx
    ON trading.ai_io_debug_log (category, call_name, created_at DESC);
CREATE TABLE IF NOT EXISTS trading.ai_model_cooldown (
    model_id TEXT NOT NULL,
    category TEXT NOT NULL,
    unavailable_until TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    failure_status TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (model_id, category)
);
CREATE INDEX IF NOT EXISTS ai_model_cooldown_until_idx
    ON trading.ai_model_cooldown (unavailable_until DESC);
"""

FAILURE_STATUSES = {"exhausted", "timeout", "error", "parse_error"}


@dataclass
class GuardDecision:
    allowed: bool
    reason: str = ""


def enabled() -> bool:
    return os.getenv("AI_COST_GUARD_ENABLED", "1").lower() not in {"0", "false", "no", "off"}


def connect():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn=None) -> None:
    own_conn = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def estimate_tokens(text: str) -> int:
    # Conservative enough for budget gates without adding tokenizer dependencies.
    return max(1, int(len(text or "") / 4))


def infer_category(name: Optional[str]) -> str:
    value = (name or "").lower()
    if value.startswith("crypto:"):
        return "trader"
    if value in {
        "chaos_bill",
        "contrarian_ricardo",
        "elliott_alex",
        "index_tracker",
        "meta_oracle",
        "passive_palych",
        "priceaction_nikita",
        "quant_diana",
        "scalper_kesha",
        "vsa_victor",
        "value_monya",
    }:
        return "trader"
    if "sentiment" in value:
        return "sentiment"
    if "daily" in value:
        return "daily_report"
    if "evolution" in value:
        return "evolution"
    if "incubator" in value:
        return "incubator"
    if "watchdog" in value:
        return "watchdog"
    if "backtest" in value:
        return "backtest"
    return "general"


def prompt_limit(category: str) -> int:
    env_key = f"AI_PROMPT_MAX_CHARS_{category.upper()}"
    defaults = {
        "trader": 8_000,
        "sentiment": 12_000,
        "daily_report": 30_000,
        "evolution": 60_000,
        "incubator": 60_000,
        "watchdog": 15_000,
        "backtest": 60_000,
        "general": 25_000,
    }
    return int(os.getenv(env_key, str(defaults.get(category, defaults["general"]))))


def hourly_limit(category: str) -> int:
    env_key = f"AI_MAX_CALLS_PER_HOUR_{category.upper()}"
    defaults = {
        "trader": 30,
        "sentiment": 4,
        "daily_report": 20,
        "evolution": 4,
        "incubator": 4,
        "watchdog": 4,
        "backtest": 3,
        "general": 20,
    }
    return int(os.getenv(env_key, str(defaults.get(category, defaults["general"]))))


def max_fallbacks(category: str) -> int:
    env_key = f"AI_MAX_FALLBACKS_{category.upper()}"
    defaults = {
        "trader": 1,
        "sentiment": 1,
        "daily_report": 2,
        "evolution": 2,
        "incubator": 2,
        "watchdog": 2,
        "backtest": 1,
        "general": 2,
    }
    return int(os.getenv(env_key, str(defaults.get(category, defaults["general"]))))


def env_int_for_category(base_key: str, category: str, default: int) -> int:
    category_key = f"{base_key}_{category.upper()}"
    return int(os.getenv(category_key, os.getenv(base_key, str(default))))


def model_cooldown_enabled() -> bool:
    return os.getenv("AI_MODEL_COOLDOWN_ENABLED", "1").lower() in {"1", "true", "yes", "on"}


def cooldown_minutes_for_failure(status: str, error_class: Optional[str], category: str) -> int:
    if not model_cooldown_enabled():
        return 0
    status = (status or "").lower()
    error_class = (error_class or "").lower()
    if status == "exhausted" or "quota" in error_class or "capacity" in error_class:
        return env_int_for_category("AI_MODEL_COOLDOWN_EXHAUSTED_MINUTES", category, 60)
    if status == "timeout":
        return env_int_for_category("AI_MODEL_COOLDOWN_TIMEOUT_MINUTES", category, 15)
    return 0


def register_model_cooldown(cur, *, model_id: Optional[str], category: str, status: str, error_class: Optional[str], error: Optional[str]) -> None:
    if not model_id:
        return
    minutes = cooldown_minutes_for_failure(status, error_class, category)
    if minutes <= 0:
        return
    reason = error_class or status
    cur.execute(
        """
        INSERT INTO trading.ai_model_cooldown
            (model_id, category, unavailable_until, reason, failure_status, failure_count, last_error, updated_at)
        VALUES (
            %s, %s, clock_timestamp() + (%s || ' minutes')::interval,
            %s, %s, 1, %s, clock_timestamp()
        )
        ON CONFLICT (model_id, category) DO UPDATE
        SET unavailable_until = GREATEST(
                trading.ai_model_cooldown.unavailable_until,
                EXCLUDED.unavailable_until
            ),
            reason = EXCLUDED.reason,
            failure_status = EXCLUDED.failure_status,
            failure_count = trading.ai_model_cooldown.failure_count + 1,
            last_error = EXCLUDED.last_error,
            updated_at = clock_timestamp()
        """,
        (model_id, category, minutes, reason, status, (error or "")[:1000] if error else None),
    )


def model_unhealthy_reason(model_id: str, category: str) -> Optional[str]:
    if not enabled():
        return None
    try:
        conn = connect()
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM trading.ai_model_cooldown
                WHERE unavailable_until <= clock_timestamp()
                """
            )
            cur.execute(
                """
                SELECT unavailable_until, reason, failure_status, failure_count
                FROM trading.ai_model_cooldown
                WHERE model_id = %s
                  AND category = %s
                  AND unavailable_until > clock_timestamp()
                LIMIT 1
                """,
                (model_id, category),
            )
            row = cur.fetchone()
            if row:
                until, reason, status, failures = row
                conn.commit()
                conn.close()
                return f"cooldown until {until.isoformat()} after {status}/{reason}, failures={failures}"

            threshold = int(os.getenv("AI_MODEL_FAILURE_THRESHOLD", "3"))
            window_minutes = int(os.getenv("AI_MODEL_HEALTH_WINDOW_MINUTES", "30"))
            cur.execute(
                """
                SELECT count(*)
                FROM trading.ai_call_log
                WHERE model_id = %s
                  AND category = %s
                  AND status = ANY(%s)
                  AND created_at > clock_timestamp() - (%s || ' minutes')::interval
                """,
                (model_id, category, list(FAILURE_STATUSES), window_minutes),
            )
            failures = cur.fetchone()[0]
        conn.commit()
        conn.close()
        if failures >= threshold:
            return f"recent failures above threshold: {failures}>={threshold} in {window_minutes}m"
        return None
    except Exception:
        return None


def preflight(prompt: str, category: str, *, call_name: Optional[str] = None, trader_name: Optional[str] = None) -> GuardDecision:
    if not enabled():
        return GuardDecision(True)
    prompt_chars = len(prompt or "")
    limit = prompt_limit(category)
    if prompt_chars > limit:
        log_call(
            category=category,
            call_name=call_name,
            trader_name=trader_name,
            model_id=None,
            prompt=prompt,
            response="",
            duration_seconds=0,
            status="budget_blocked",
            error_class="prompt_too_large",
            error=f"prompt_chars={prompt_chars} limit={limit}",
            request_allowed=False,
        )
        return GuardDecision(False, f"prompt too large: {prompt_chars}>{limit}")

    try:
        conn = connect()
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM trading.ai_call_log
                WHERE category = %s
                  AND request_allowed = TRUE
                  AND status NOT IN ('model_skipped', 'budget_blocked')
                  AND created_at > clock_timestamp() - interval '1 hour'
                """,
                (category,),
            )
            count = cur.fetchone()[0]
        conn.close()
    except Exception as exc:
        # If accounting storage is briefly unavailable, do not break trading.
        return GuardDecision(True, f"guard accounting unavailable: {type(exc).__name__}: {exc}")

    limit = hourly_limit(category)
    if count >= limit:
        log_call(
            category=category,
            call_name=call_name,
            trader_name=trader_name,
            model_id=None,
            prompt=prompt,
            response="",
            duration_seconds=0,
            status="budget_blocked",
            error_class="hourly_limit",
            error=f"calls_last_hour={count} limit={limit}",
            request_allowed=False,
        )
        return GuardDecision(False, f"hourly call limit reached: {count}>={limit}")
    return GuardDecision(True)


def model_unhealthy(model_id: str, category: str) -> bool:
    return model_unhealthy_reason(model_id, category) is not None


def log_model_skipped(*, category: str, call_name: Optional[str], trader_name: Optional[str], model_id: str, prompt: str, reason: str, fallback_index: int) -> None:
    log_call(
        category=category,
        call_name=call_name,
        trader_name=trader_name,
        model_id=model_id,
        prompt="",
        response="",
        duration_seconds=0,
        status="model_skipped",
        error_class="model_unhealthy",
        error=reason,
        fallback_index=fallback_index,
        request_allowed=False,
    )


def log_call(
    *,
    category: str,
    call_name: Optional[str],
    trader_name: Optional[str],
    model_id: Optional[str],
    prompt: str,
    response: str,
    duration_seconds: Optional[float],
    status: str,
    error_class: Optional[str] = None,
    error: Optional[str] = None,
    fallback_index: Optional[int] = None,
    request_allowed: bool = True,
) -> None:
    if not enabled():
        return
    try:
        conn = connect()
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trading.ai_call_log
                    (script_name, call_name, trader_name, category, model_id,
                     prompt_chars, prompt_tokens_est, response_chars, duration_seconds,
                     status, error_class, error, fallback_index, request_allowed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    os.path.basename(os.getenv("AI_CALL_SCRIPT", "") or sys.argv[0]) or None,
                    call_name,
                    trader_name,
                    category,
                    model_id,
                    len(prompt or ""),
                    estimate_tokens(prompt or ""),
                    len(response or ""),
                    duration_seconds,
                    status,
                    error_class,
                    (error or "")[:1000] if error else None,
                    fallback_index,
                    request_allowed,
                ),
            )
            register_model_cooldown(
                cur,
                model_id=model_id,
                category=category,
                status=status,
                error_class=error_class,
                error=error,
            )
            if model_id and status == "success":
                cur.execute(
                    """
                    DELETE FROM trading.ai_model_cooldown
                    WHERE model_id = %s
                      AND category = %s
                    """,
                    (model_id, category),
                )
            if debug_io_enabled():
                prompt_text, prompt_truncated = debug_clip(prompt or "")
                response_text, response_truncated = debug_clip(response or "")
                cur.execute(
                    """
                    INSERT INTO trading.ai_io_debug_log
                        (script_name, call_name, trader_name, category, model_id, status,
                         prompt_chars, response_chars, prompt_text, response_text, truncated)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        os.path.basename(os.getenv("AI_CALL_SCRIPT", "") or sys.argv[0]) or None,
                        call_name,
                        trader_name,
                        category,
                        model_id,
                        status,
                        len(prompt or ""),
                        len(response or ""),
                        prompt_text,
                        response_text,
                        prompt_truncated or response_truncated,
                    ),
                )
        conn.commit()
        conn.close()
    except Exception:
        return


def debug_io_enabled() -> bool:
    return os.getenv("AI_DEBUG_IO_LOG", "0").lower() in {"1", "true", "yes", "on"}


def debug_clip(text: str) -> tuple[str, bool]:
    limit = int(os.getenv("AI_DEBUG_IO_MAX_CHARS", "60000"))
    if len(text or "") <= limit:
        return text or "", False
    return (text or "")[:limit], True


class timer:
    def __enter__(self):
        self.started = time.monotonic()
        return self

    def __exit__(self, *_):
        self.duration = round(time.monotonic() - self.started, 3)
