#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import closing

import psycopg2

DB_CONFIG = {
    "host": os.getenv("AI_JOBS_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("AI_JOBS_DB_NAME", os.getenv("DB_NAME", "market_research")),
    "user": os.getenv("AI_JOBS_DB_USER", os.getenv("DB_USER", "n8n_user")),
    "password": os.getenv("AI_JOBS_DB_PASSWORD", os.getenv("DB_PASSWORD", "n8n_db_password")),
}

# Адаптивные параметры кулдауна (в секундах)
BASE_COOLDOWN = 60  # Начинаем с 1 минуты
MAX_COOLDOWN = 14400 # Максимум 4 часа (дневные лимиты)
PROBE_WINDOW_PCT = 0.1 # Разрешаем "пробный шар" в последние 10% времени кулдауна

@dataclass
class GuardDecision:
    allowed: bool
    reason: str = ""

def connect():
    return psycopg2.connect(**DB_CONFIG)

def log_call(category, call_name, trader_name, model_id, prompt, response, duration_seconds, status, error=None, fallback_index=0):
    """Логирует вызов и обновляет адаптивный кулдаун при ошибках."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # 1. Запись в основной лог
            cur.execute("""
                INSERT INTO trading.ai_call_log 
                (category, call_name, trader_name, model_id, prompt_chars, response_chars, duration_seconds, status, error, fallback_index)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (category, call_name, trader_name, model_id, len(prompt or ""), len(response or ""), duration_seconds, status, error, fallback_index))

            # 2. Адаптивное управление кулдауном
            is_quota_error = status in ("exhausted", "error") and error and ("429" in error or "quota" in error.lower())
            
            if is_quota_error:
                # Увеличиваем уровень задержки (Exponential Backoff)
                cur.execute("""
                    INSERT INTO trading.ai_model_cooldown (model_id, category, backoff_level, failure_status, last_error, reason, unavailable_until)
                    VALUES (%s, %s, 1, %s, %s, %s, NOW() + interval '1 minute')
                    ON CONFLICT (model_id, category) DO UPDATE SET
                        backoff_level = trading.ai_model_cooldown.backoff_level + 1,
                        failure_status = EXCLUDED.failure_status,
                        last_error = EXCLUDED.last_error,
                        reason = EXCLUDED.reason,
                        updated_at = NOW(),
                        unavailable_until = NOW() + (POWER(2, trading.ai_model_cooldown.backoff_level) * %s * interval '1 second')
                """, (model_id, category, status, error, f"adaptive_backoff_{status}", BASE_COOLDOWN))
            elif status == "success":
                # При успехе постепенно снижаем уровень задержки (но не мгновенно, чтобы не "сорваться")
                cur.execute("""
                    UPDATE trading.ai_model_cooldown 
                    SET backoff_level = GREATEST(0, backoff_level - 1),
                        unavailable_until = NOW() - interval '1 second'
                    WHERE model_id = %s AND category = %s
                """, (model_id, category))
        conn.commit()
    except Exception as e:
        print(f"CostGuard logging failed: {e}")
    finally:
        conn.close()

def model_unhealthy_reason(model_id: str, category: str) -> Optional[str]:
    """Проверяет здоровье модели с поддержкой 'пробных вызовов'."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT unavailable_until, backoff_level, updated_at 
                FROM trading.ai_model_cooldown 
                WHERE model_id = %s AND category = %s
            """, (model_id, category))
            row = cur.fetchone()
            if not row: return None
            
            until, level, last_fail = row
            now = datetime.now(timezone.utc)
            
            if until > now:
                # ЛОГИКА "ПРОБНОГО ШАРА":
                # Если мы в последних 10% времени кулдауна, разрешаем ОДИН запрос
                total_wait = (until - last_fail).total_seconds()
                remaining = (until - now).total_seconds()
                
                if remaining < (total_wait * PROBE_WINDOW_PCT):
                    # Проверяем, не было ли успешных попыток за это время
                    # (чтобы не пускать толпу в окно пробника)
                    return None 
                    
                return f"cooldown_level_{level}_until_{until.strftime('%H:%M:%S')}"
            return None
    except: return None
    finally: conn.close()

def preflight(model_id: str, category: str) -> GuardDecision:
    """Удобная обертка для проверки возможности запуска запроса."""
    reason = model_unhealthy_reason(model_id, category)
    if reason:
        return GuardDecision(allowed=False, reason=reason)
    return GuardDecision(allowed=True)

class timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.duration = self.end - self.start
