#!/usr/bin/env python3
import json
import math
import os
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

from ai_cost_guard import hourly_limit
from ai_job_store import connect, encode_command, ensure_schema


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN = os.getenv("AI_JOB_PYTHON", "/home/user/trading_venv/bin/python")
WORKER = os.getenv("AI_JOB_WORKER", os.path.join(BASE_DIR, "ai_job_worker.py"))
RUN_AI_TRADER = os.getenv("AI_JOB_RUN_AI_TRADER", os.path.join(BASE_DIR, "run_ai_trader_once.sh"))
RUN_AI_CRYPTO_TRADER = os.getenv("AI_JOB_RUN_AI_CRYPTO_TRADER", os.path.join(BASE_DIR, "run_ai_crypto_trader_once.sh"))
RUN_HOURLY_REPORT = os.getenv("AI_JOB_RUN_HOURLY_REPORT", os.path.join(BASE_DIR, "run_hourly_report_once.sh"))
RUN_CRYPTO_HOURLY_REPORT = os.getenv("AI_JOB_RUN_CRYPTO_HOURLY_REPORT", os.path.join(BASE_DIR, "run_crypto_hourly_report_once.sh"))
MAX_WORKERS = int(os.getenv("AI_JOB_MAX_WORKERS", "2"))
START_BATCH = int(os.getenv("AI_JOB_START_BATCH", "1"))
MAX_QUEUE_AGE_MINUTES = int(os.getenv("AI_JOB_MAX_QUEUE_AGE_MINUTES", "20"))
MAX_RUNNING_MINUTES = int(os.getenv("AI_JOB_MAX_RUNNING_MINUTES", "15"))
ENABLE_CRYPTO_AI = os.getenv("AI_ENABLE_CRYPTO_AI", "0").lower() in {"1", "true", "yes", "on"}
FULL_WAVE_INTERVAL_MINUTES = int(os.getenv("AI_JOB_FULL_WAVE_INTERVAL_MINUTES", "90"))
FAST_WAVE_INTERVAL_MINUTES = int(os.getenv("AI_JOB_FAST_WAVE_INTERVAL_MINUTES", "10"))
EVENT_WAVE_INTERVAL_MINUTES = int(os.getenv("AI_JOB_EVENT_WAVE_INTERVAL_MINUTES", "10"))
MIN_TRADER_TTL_MINUTES = int(os.getenv("AI_JOB_MIN_TRADER_TTL_MINUTES", "20"))
FULL_TRADER_TTL_MINUTES = int(os.getenv("AI_JOB_FULL_TRADER_TTL_MINUTES", str(MIN_TRADER_TTL_MINUTES)))
FAST_TRADER_TTL_MINUTES = int(os.getenv("AI_JOB_FAST_TRADER_TTL_MINUTES", "8"))
EVENT_TRADER_TTL_MINUTES = int(os.getenv("AI_JOB_EVENT_TRADER_TTL_MINUTES", "5"))
EVENT_FIVE_MIN_CHANGE_PCT = float(os.getenv("AI_JOB_EVENT_FIVE_MIN_CHANGE_PCT", "0.25"))
EVENT_HOUR_CHANGE_PCT = float(os.getenv("AI_JOB_EVENT_HOUR_CHANGE_PCT", "0.7"))
LOG_IDLE_DECISIONS = os.getenv("AI_JOB_LOG_IDLE_DECISIONS", "1").lower() in {"1", "true", "yes", "on"}
BUDGET_AWARE_DISPATCH = os.getenv("AI_JOB_BUDGET_AWARE", "1").lower() in {"1", "true", "yes", "on"}
AI_REQUESTS_PER_TRADER_ESTIMATE = float(os.getenv("AI_JOB_AI_REQUESTS_PER_TRADER_ESTIMATE", "2.0"))
AI_CALL_RESERVE_TRADER = int(os.getenv("AI_JOB_AI_CALL_RESERVE_TRADER", "2"))
TZ = ZoneInfo(os.getenv("AI_JOB_TZ", "Europe/Moscow"))

DISPATCHER_LOG_DDL = """
CREATE TABLE IF NOT EXISTS trading.ai_dispatcher_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    tick_at TIMESTAMPTZ NOT NULL,
    market TEXT NOT NULL,
    decision TEXT NOT NULL,
    wave_reason TEXT,
    inserted INTEGER NOT NULL DEFAULT 0,
    due_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0,
    running_count INTEGER NOT NULL DEFAULT 0,
    queued_count INTEGER NOT NULL DEFAULT 0,
    five_min_change_pct NUMERIC,
    hour_change_pct NUMERIC,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ai_dispatcher_log_created_idx
    ON trading.ai_dispatcher_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_dispatcher_log_market_tick_idx
    ON trading.ai_dispatcher_log (market, tick_at DESC);
"""

MOEX_TRADERS = [
    "Chaos_Bill",
    "Contrarian_Ricardo",
    "Elliott_Alex",
    "Index_Tracker",
    "Meta_Oracle",
    "Passive_Palych",
    "PriceAction_Nikita",
    "Quant_Diana",
    "Scalper_Kesha",
    "VSA_Victor",
    "Value_Monya",
]
CRYPTO_TRADERS = list(MOEX_TRADERS)


def csv_list(env_name, default_items):
    configured = os.getenv(env_name)
    if not configured:
        return list(default_items)
    return [item.strip() for item in configured.split(",") if item.strip()]


FAST_TRADERS = csv_list("AI_JOB_FAST_TRADERS", [
    "Scalper_Kesha",
    "PriceAction_Nikita",
    "VSA_Victor",
    "Quant_Diana",
    "Contrarian_Ricardo",
    "Meta_Oracle",
])
EVENT_TRADERS = csv_list("AI_JOB_EVENT_TRADERS", FAST_TRADERS)


def log(message):
    print(f"[ {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} ] {message}", flush=True)


def ensure_dispatcher_log_schema(conn):
    with conn.cursor() as cur:
        cur.execute(DISPATCHER_LOG_DDL)
    conn.commit()


def is_moex_session(now):
    # Продвинутая проверка сессии через производственный календарь (XMOS = Moscow Exchange)
    moex = mcal.get_calendar('XMOS')
    # Используем дату в локальной зоне для запроса расписания
    schedule = moex.schedule(start_date=now.date(), end_date=now.date())
    if schedule.empty:
        return False
    
    # MOEX обычно торгуется до 23:50. Берем время закрытия из расписания
    market_open = schedule.iloc[0]['market_open']
    market_close = schedule.iloc[0]['market_close']
    
    # Конвертируем 'now' в UTC для корректного сравнения с расписанием
    now_utc = now.astimezone(ZoneInfo("UTC"))
    
    # Запас в 10 минут до закрытия (чтобы не открывать позиции в последние минуты)
    effective_close = market_close - timedelta(minutes=10)
    
    return market_open <= now_utc <= effective_close

def check_data_readiness(conn, now):
    # Pre-flight Readiness Gate: проверяем, что данные свежие
    with conn.cursor() as cur:
        cur.execute("SELECT max(updated_at) FROM analytics.trader_market_windows")
        last_update = cur.fetchone()[0]
    
    if not last_update:
        return False
        
    # Данные должны быть не старше 30 минут от текущего времени
    age_minutes = (now.astimezone(ZoneInfo("UTC")) - last_update.astimezone(ZoneInfo("UTC"))).total_seconds() / 60
    if age_minutes > 30:
        log(f"Data readiness failed: Market data is {age_minutes:.1f} minutes old.")
        return False
    return True

def bucket(now):
    return now.replace(second=0, microsecond=0)


def interval_due(now, interval_minutes):
    if interval_minutes <= 0:
        return False
    local_minute = now.hour * 60 + now.minute
    return local_minute % interval_minutes == 0


def enqueue_job(conn, job_key, market, job_type, priority, command, log_path, scheduled_for, trader_name=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trading.ai_jobs
                (job_key, market, job_type, trader_name, priority, command, log_path, scheduled_for)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_key) DO NOTHING
            """,
            (job_key, market, job_type, trader_name, priority, encode_command(command), log_path, scheduled_for),
        )
        inserted = cur.rowcount > 0
    conn.commit()
    return inserted


def active_trader_job_counts(conn, market):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, count(*)
            FROM trading.ai_jobs
            WHERE market = %s
              AND job_type = 'trader'
              AND status IN ('queued', 'running')
            GROUP BY status
            """,
            (market,),
        )
        rows = dict(cur.fetchall())
    queued = int(rows.get("queued", 0))
    running = int(rows.get("running", 0))
    return {
        "queued": queued,
        "running": running,
        "pending": queued + running,
    }


def pending_trader_jobs(conn, market):
    return active_trader_job_counts(conn, market)["pending"]


def last_trader_job_created(conn, market, trader_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT created_at
            FROM trading.ai_jobs
            WHERE market = %s
              AND job_type = 'trader'
              AND trader_name = %s
              AND status IN ('queued', 'running', 'succeeded', 'failed', 'stale')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (market, trader_name),
        )
        row = cur.fetchone()
        return row[0] if row else None


def due_traders(conn, market, traders, now, ttl_minutes):
    due = []
    ttl = timedelta(minutes=ttl_minutes)
    for trader in traders:
        last_created = last_trader_job_created(conn, market, trader)
        if last_created is None or now - last_created.astimezone(TZ) >= ttl:
            due.append(trader)
    return due


def moex_market_move_metrics(conn):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(max(abs(five_min_change_pct)), 0),
                    COALESCE(max(abs(hour_change_pct)), 0)
                FROM analytics.trader_market_context_v
                WHERE active = TRUE
                  AND engine = 'stock'
                """
            )
            five_min, hour = cur.fetchone()
    except Exception as exc:
        log(f"MOEX event gate unavailable: {type(exc).__name__}: {exc}")
        return {"five_min": 0.0, "hour": 0.0, "error": f"{type(exc).__name__}: {exc}"}
    return {"five_min": float(five_min or 0), "hour": float(hour or 0), "error": None}


def moex_event_active(metrics):
    return (
        metrics["five_min"] >= EVENT_FIVE_MIN_CHANGE_PCT
        or metrics["hour"] >= EVENT_HOUR_CHANGE_PCT
    )


def dispatcher_config():
    return {
        "full_interval_min": FULL_WAVE_INTERVAL_MINUTES,
        "fast_interval_min": FAST_WAVE_INTERVAL_MINUTES,
        "event_interval_min": EVENT_WAVE_INTERVAL_MINUTES,
        "full_ttl_min": FULL_TRADER_TTL_MINUTES,
        "fast_ttl_min": FAST_TRADER_TTL_MINUTES,
        "event_ttl_min": EVENT_TRADER_TTL_MINUTES,
        "event_5m_pct": EVENT_FIVE_MIN_CHANGE_PCT,
        "event_1h_pct": EVENT_HOUR_CHANGE_PCT,
        "max_workers": MAX_WORKERS,
        "start_batch": START_BATCH,
        "budget_aware": BUDGET_AWARE_DISPATCH,
        "ai_requests_per_trader_estimate": AI_REQUESTS_PER_TRADER_ESTIMATE,
        "ai_call_reserve_trader": AI_CALL_RESERVE_TRADER,
        "fast_traders": FAST_TRADERS,
        "event_traders": EVENT_TRADERS,
    }


def trader_ai_budget(conn):
    if not BUDGET_AWARE_DISPATCH:
        return {"enabled": False}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM trading.ai_call_log
                WHERE category = 'trader'
                  AND request_allowed = TRUE
                  AND status NOT IN ('model_skipped', 'budget_blocked')
                  AND created_at > clock_timestamp() - interval '1 hour'
                """
            )
            used = int(cur.fetchone()[0] or 0)
        limit = hourly_limit("trader")
        remaining = max(0, limit - used - AI_CALL_RESERVE_TRADER)
        return {
            "enabled": True,
            "limit": limit,
            "used": used,
            "reserve": AI_CALL_RESERVE_TRADER,
            "remaining": remaining,
            "requests_per_trader_estimate": AI_REQUESTS_PER_TRADER_ESTIMATE,
        }
    except Exception as exc:
        log(f"AI budget gate unavailable: {type(exc).__name__}: {exc}")
        return {"enabled": False, "error": f"{type(exc).__name__}: {exc}"}


def estimated_ai_requests(trader_count):
    return int(math.ceil(max(0, trader_count) * AI_REQUESTS_PER_TRADER_ESTIMATE))


def ai_budget_allows_wave(budget, trader_count):
    if not budget.get("enabled"):
        return True
    return budget.get("remaining", 0) >= estimated_ai_requests(trader_count)


def record_dispatcher_decision(
    conn,
    *,
    tick,
    market,
    decision,
    wave_reason=None,
    inserted=0,
    due_count=0,
    candidate_count=0,
    counts=None,
    metrics=None,
    details=None,
):
    counts = counts or {"pending": 0, "queued": 0, "running": 0}
    metrics = metrics or {"five_min": None, "hour": None}
    details = details or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trading.ai_dispatcher_log
                (tick_at, market, decision, wave_reason, inserted, due_count, candidate_count,
                 pending_count, running_count, queued_count, five_min_change_pct, hour_change_pct,
                 config, details)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            """,
            (
                tick,
                market,
                decision,
                wave_reason,
                inserted,
                due_count,
                candidate_count,
                int(counts.get("pending", 0)),
                int(counts.get("running", 0)),
                int(counts.get("queued", 0)),
                metrics.get("five_min"),
                metrics.get("hour"),
                json.dumps(dispatcher_config(), ensure_ascii=False),
                json.dumps(details, ensure_ascii=False),
            ),
        )
    conn.commit()


def queue_moex_traders(conn, traders, tick, tick_key, reason, priority=100):
    inserted = 0
    for trader in traders:
        inserted += int(enqueue_job(
            conn,
            f"moex:trader:{reason}:{trader}:{tick_key}",
            "moex",
            "trader",
            priority,
            [RUN_AI_TRADER, trader],
            f"/home/user/logs/traders/{trader}.log",
            tick,
            trader,
        ))
    if inserted:
        log(f"Queued MOEX trader {reason} wave {tick_key}: inserted={inserted}, due={len(traders)}.")
    return inserted


def queue_moex_wave(
    conn,
    traders,
    *,
    tick,
    tick_key,
    reason,
    priority,
    candidate_count,
    counts,
    metrics,
    extra_details=None,
):
    details = {"tick_key": tick_key}
    if extra_details:
        details.update(extra_details)

    if not traders:
        record_dispatcher_decision(
            conn,
            tick=tick,
            market="moex",
            decision="no_due_traders",
            wave_reason=reason,
            inserted=0,
            due_count=0,
            candidate_count=candidate_count,
            counts=counts,
            metrics=metrics,
            details=details,
        )
        return 0

    budget = trader_ai_budget(conn)
    required = estimated_ai_requests(len(traders))
    details["ai_budget"] = {**budget, "required": required}
    if not ai_budget_allows_wave(budget, len(traders)):
        log(
            f"Skipped MOEX trader {reason} wave {tick_key}: "
            f"AI budget remaining={budget.get('remaining', 0)}, required={required}."
        )
        record_dispatcher_decision(
            conn,
            tick=tick,
            market="moex",
            decision="skipped_ai_budget",
            wave_reason=reason,
            inserted=0,
            due_count=len(traders),
            candidate_count=candidate_count,
            counts=counts,
            metrics=metrics,
            details=details,
        )
        return 0

    inserted = queue_moex_traders(conn, traders, tick, tick_key, reason, priority=priority)
    record_dispatcher_decision(
        conn,
        tick=tick,
        market="moex",
        decision="queued" if inserted else "no_due_traders",
        wave_reason=reason,
        inserted=inserted,
        due_count=len(traders),
        candidate_count=candidate_count,
        counts=counts,
        metrics=metrics,
        details=details,
    )
    return inserted


def queue_shadow_traders(conn, tick, tick_key):
    """Постановка в очередь теневых клонов из таблицы shadow_portfolio."""
    inserted = 0
    with conn.cursor() as cur:
        cur.execute("SELECT trader_name FROM trading.shadow_portfolio WHERE is_active = TRUE")
        shadow_traders = [r[0] for r in cur.fetchall()]
        
    for trader in shadow_traders:
        inserted += int(enqueue_job(
            conn,
            f"shadow:trader:{trader}:{tick_key}",
            "moex",
            "trader",
            50, # Ниже приоритет чем у основных
            [RUN_AI_TRADER, "--shadow", trader],
            f"/home/user/logs/traders/shadow_{trader}.log",
            tick,
            trader,
        ))
    if inserted:
        log(f"Queued SHADOW trader wave {tick_key}: inserted={inserted}.")
    return inserted


def enqueue_due_jobs(conn, now):
    tick = bucket(now)
    tick_key = tick.strftime("%Y%m%d%H%M")

    if is_moex_session(now):
        metrics = moex_market_move_metrics(conn)
        counts = active_trader_job_counts(conn, "moex")
        
        # Запуск теневых клонов (параллельно с основными, если есть место в пуле)
        # Мы запускаем их каждую быструю волну (например раз в 10 мин)
        if interval_due(now, FAST_WAVE_INTERVAL_MINUTES):
            queue_shadow_traders(conn, tick, tick_key)

        if counts["pending"]:
            if now.second < 10:
                log(f"Skipped MOEX trader wave {tick_key}: pending={counts['pending']}.")
                record_dispatcher_decision(
                    conn,
                    tick=tick,
                    market="moex",
                    decision="skipped_pending",
                    counts=counts,
                    metrics=metrics,
                    details={"tick_key": tick_key},
                )
        else:
            if interval_due(now, FULL_WAVE_INTERVAL_MINUTES):
                traders = due_traders(conn, "moex", MOEX_TRADERS, now, FULL_TRADER_TTL_MINUTES)
                queue_moex_wave(
                    conn,
                    traders,
                    tick=tick,
                    tick_key=tick_key,
                    reason="full",
                    priority=100,
                    candidate_count=len(MOEX_TRADERS),
                    counts=counts,
                    metrics=metrics,
                )
            elif interval_due(now, EVENT_WAVE_INTERVAL_MINUTES) and moex_event_active(metrics):
                traders = due_traders(conn, "moex", EVENT_TRADERS, now, EVENT_TRADER_TTL_MINUTES)
                queue_moex_wave(
                    conn,
                    traders,
                    tick=tick,
                    tick_key=tick_key,
                    reason="event",
                    priority=120,
                    candidate_count=len(EVENT_TRADERS),
                    counts=counts,
                    metrics=metrics,
                    extra_details={"event_active": True},
                )
            elif interval_due(now, FAST_WAVE_INTERVAL_MINUTES):
                traders = due_traders(conn, "moex", FAST_TRADERS, now, FAST_TRADER_TTL_MINUTES)
                queue_moex_wave(
                    conn,
                    traders,
                    tick=tick,
                    tick_key=tick_key,
                    reason="fast",
                    priority=110,
                    candidate_count=len(FAST_TRADERS),
                    counts=counts,
                    metrics=metrics,
                )
            elif LOG_IDLE_DECISIONS and now.second < 10:
                record_dispatcher_decision(
                    conn,
                    tick=tick,
                    market="moex",
                    decision="no_wave_due",
                    counts=counts,
                    metrics=metrics,
                    details={
                        "tick_key": tick_key,
                        "event_active": moex_event_active(metrics),
                    },
                )

    if ENABLE_CRYPTO_AI and now.minute % 5 == 2:
        pending = pending_trader_jobs(conn, "crypto")
        if pending:
            if now.second < 10:
                log(f"Skipped crypto trader wave {tick_key}: pending={pending}.")
        else:
            priority = 40 if is_moex_session(now) else 70
            inserted = 0
            for trader in due_traders(conn, "crypto", CRYPTO_TRADERS, now, MIN_TRADER_TTL_MINUTES):
                inserted += int(enqueue_job(
                    conn,
                    f"crypto:trader:{trader}:{tick_key}",
                    "crypto",
                    "trader",
                    priority,
                    [RUN_AI_CRYPTO_TRADER, trader],
                    f"/home/user/logs/traders/crypto_{trader}.log",
                    tick,
                    trader,
                ))
            if inserted:
                log(f"Queued crypto trader wave {tick_key}: inserted={inserted}.")

    if is_moex_session(now) and now.minute == 0:
        enqueue_job(
            conn,
            f"moex:hourly_report:{tick_key}",
            "moex",
            "hourly_report",
            80,
            [RUN_HOURLY_REPORT],
            "/home/user/logs/traders/hourly_report.log",
            tick,
        )

    if ENABLE_CRYPTO_AI and now.minute in (2, 32):
        enqueue_job(
            conn,
            f"crypto:hourly_report:{tick_key}",
            "crypto",
            "hourly_report",
            30,
            [RUN_CRYPTO_HOURLY_REPORT],
            "/home/user/logs/traders/crypto_hourly_report.log",
            tick,
        )


def mark_stale(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE trading.ai_jobs
            SET status = 'stale',
                error = COALESCE(error, 'running job exceeded max runtime'),
                finished_at = now(),
                updated_at = now()
            WHERE status = 'running'
              AND started_at < now() - (%s || ' minutes')::interval
            """,
            (MAX_RUNNING_MINUTES,),
        )
        stale_running = cur.rowcount
        cur.execute(
            """
            UPDATE trading.ai_jobs
            SET status = 'skipped',
                error = COALESCE(error, 'queued job exceeded max queue age'),
                finished_at = now(),
                updated_at = now()
            WHERE status = 'queued'
              AND scheduled_for < now() - (%s || ' minutes')::interval
            """,
            (MAX_QUEUE_AGE_MINUTES,),
        )
        skipped = cur.rowcount
    conn.commit()
    if stale_running or skipped:
        log(f"Marked stale_running={stale_running}, skipped_queued={skipped}.")


def start_available_jobs(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM trading.ai_jobs WHERE status = 'running'")
        running = cur.fetchone()[0]
        available = max(0, MAX_WORKERS - running)
        if available <= 0:
            log(f"Worker pool full: running={running}, max={MAX_WORKERS}.")
            return
        start_limit = min(available, max(1, START_BATCH))

        cur.execute(
            """
            SELECT id
            FROM trading.ai_jobs
            WHERE status = 'queued'
              AND scheduled_for <= now()
              AND (%s OR market != 'crypto')
            ORDER BY priority DESC, scheduled_for ASC, id ASC
            LIMIT %s
            """,
            (ENABLE_CRYPTO_AI, start_limit),
        )
        ids = [row[0] for row in cur.fetchall()]

        for job_id in ids:
            cur.execute(
                """
                UPDATE trading.ai_jobs
                SET status = 'running',
                    started_at = now(),
                    heartbeat_at = now(),
                    updated_at = now()
                WHERE id = %s AND status = 'queued'
                RETURNING id
                """,
                (job_id,),
            )
            if not cur.fetchone():
                continue
            conn.commit()
            try:
                subprocess.Popen(
                    [PYTHON_BIN, WORKER, str(job_id)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                log(f"Started AI job {job_id}.")
            except Exception as exc:
                cur.execute(
                    """
                    UPDATE trading.ai_jobs
                    SET status = 'failed',
                        error = %s,
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (f"dispatcher failed to spawn worker: {type(exc).__name__}: {exc}", job_id),
                )
                conn.commit()


def check_system_ready(conn):
    """Проверка глобального флага готовности системы из Heartbeat."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM trading.system_status WHERE key = 'system_ready'")
            row = cur.fetchone()
            return row[0] if row else False
    except: return False

def main():
    conn = connect()
    try:
        ensure_schema(conn)
        ensure_dispatcher_log_schema(conn)
        now = datetime.now(TZ)
        
        # 1. Проверка блокировки системы (Safety Gate)
        if is_moex_session(now) and not check_system_ready(conn):
            log("CRITICAL: System is NOT READY (Heartbeat failed). Blocking all trades.")
            return

        # 2. Pre-flight Readiness Gate (Свежесть данных)
        if is_moex_session(now) and not check_data_readiness(conn, now):
            log("Readiness Gate FAILED. Skipping dispatch cycle.")
            return

        enqueue_due_jobs(conn, now)
        mark_stale(conn)
        start_available_jobs(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
