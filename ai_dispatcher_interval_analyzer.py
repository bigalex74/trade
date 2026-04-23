#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from ai_cost_guard import ensure_schema as ensure_ai_call_schema
from ai_cost_guard import hourly_limit
from ai_job_dispatcher import DISPATCHER_LOG_DDL, EVENT_TRADERS, FAST_TRADERS, MOEX_TRADERS
from ai_job_store import connect, ensure_schema as ensure_job_schema


TZ = ZoneInfo(os.getenv("AI_JOB_TZ", "Europe/Moscow"))
DEFAULT_JOB_SECONDS = float(os.getenv("AI_INTERVAL_ANALYZER_DEFAULT_JOB_SECONDS", "120"))
DEFAULT_EVENT_ACTIVE_FRACTION = float(os.getenv("AI_INTERVAL_ANALYZER_DEFAULT_EVENT_ACTIVE_FRACTION", "0.25"))


def parse_csv_ints(value: str) -> list[int]:
    result = []
    for item in (value or "").split(","):
        item = item.strip()
        if item:
            result.append(int(item))
    return result


def percentile(values: list[float], pct: float) -> float | None:
    clean = sorted(v for v in values if v is not None and v >= 0)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * pct
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return clean[int(pos)]
    return clean[lower] + (clean[upper] - clean[lower]) * (pos - lower)


def fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def ensure_dispatcher_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DISPATCHER_LOG_DDL)
    conn.commit()


def fetch_jobs(conn, window_minutes: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                status,
                trader_name,
                EXTRACT(EPOCH FROM (started_at - created_at)) AS queue_delay_seconds,
                COALESCE(
                    duration_seconds,
                    EXTRACT(EPOCH FROM (finished_at - started_at))
                ) AS duration_seconds,
                error
            FROM trading.ai_jobs
            WHERE market = 'moex'
              AND job_type = 'trader'
              AND created_at >= now() - (%s || ' minutes')::interval
            """,
            (window_minutes,),
        )
        rows = cur.fetchall()
    return [
        {
            "status": row[0],
            "trader_name": row[1],
            "queue_delay_seconds": float(row[2]) if row[2] is not None else None,
            "duration_seconds": float(row[3]) if row[3] is not None else None,
            "error": row[4],
        }
        for row in rows
    ]


def fetch_calls(conn, window_minutes: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                status,
                request_allowed,
                error_class,
                model_id,
                prompt_chars,
                prompt_tokens_est,
                response_chars,
                duration_seconds,
                fallback_index
            FROM trading.ai_call_log
            WHERE category = 'trader'
              AND created_at >= now() - (%s || ' minutes')::interval
            """,
            (window_minutes,),
        )
        rows = cur.fetchall()
    return [
        {
            "status": row[0],
            "request_allowed": bool(row[1]),
            "error_class": row[2],
            "model_id": row[3],
            "prompt_chars": int(row[4] or 0),
            "prompt_tokens_est": int(row[5] or 0),
            "response_chars": int(row[6] or 0),
            "duration_seconds": float(row[7]) if row[7] is not None else None,
            "fallback_index": int(row[8]) if row[8] is not None else None,
        }
        for row in rows
    ]


def fetch_dispatcher_rows(conn, window_minutes: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                decision,
                wave_reason,
                inserted,
                due_count,
                candidate_count,
                pending_count,
                running_count,
                queued_count,
                five_min_change_pct,
                hour_change_pct,
                details
            FROM trading.ai_dispatcher_log
            WHERE market = 'moex'
              AND created_at >= now() - (%s || ' minutes')::interval
            """,
            (window_minutes,),
        )
        rows = cur.fetchall()
    return [
        {
            "decision": row[0],
            "wave_reason": row[1],
            "inserted": int(row[2] or 0),
            "due_count": int(row[3] or 0),
            "candidate_count": int(row[4] or 0),
            "pending_count": int(row[5] or 0),
            "running_count": int(row[6] or 0),
            "queued_count": int(row[7] or 0),
            "five_min_change_pct": float(row[8]) if row[8] is not None else None,
            "hour_change_pct": float(row[9]) if row[9] is not None else None,
            "details": row[10] or {},
        }
        for row in rows
    ]


def fetch_active_cooldowns(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                model_id,
                category,
                unavailable_until,
                reason,
                failure_status,
                failure_count
            FROM trading.ai_model_cooldown
            WHERE unavailable_until > clock_timestamp()
            ORDER BY category, unavailable_until DESC, model_id
            """
        )
        rows = cur.fetchall()
    return [
        {
            "model_id": row[0],
            "category": row[1],
            "unavailable_until": row[2].isoformat() if row[2] else None,
            "reason": row[3],
            "failure_status": row[4],
            "failure_count": int(row[5] or 0),
        }
        for row in rows
    ]


def event_active_fraction(rows: list[dict]) -> tuple[float, str]:
    values = []
    for row in rows:
        details = row.get("details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = {}
        if "event_active" in details:
            values.append(bool(details["event_active"]))
    if values:
        return sum(values) / len(values), "observed dispatcher details"

    event_checks = [row for row in rows if row["wave_reason"] == "event"]
    if event_checks:
        queued = sum(1 for row in event_checks if row["inserted"] > 0 or row["decision"] == "queued")
        return queued / len(event_checks), "observed event rows"

    return DEFAULT_EVENT_ACTIVE_FRACTION, "fallback env/default"


def effective_due(last_created_minute: int | None, minute: int, ttl_minutes: int) -> bool:
    return last_created_minute is None or minute - last_created_minute >= ttl_minutes


def simulate_schedule(
    *,
    full_interval: int,
    fast_interval: int,
    event_interval: int,
    full_ttl: int,
    fast_ttl: int,
    event_ttl: int,
    max_workers: int,
    start_batch: int,
    dispatch_ticks: int,
    job_seconds: float,
    event_fraction: float,
    minutes: int = 24 * 60,
) -> dict:
    last_created = {trader: None for trader in MOEX_TRADERS}
    busy_until_minute = -1
    event_accumulator = 0.0
    jobs = 0
    waves = Counter()
    skipped = Counter()
    no_due = Counter()
    wave_jobs = []

    for minute in range(minutes):
        pending = minute < busy_until_minute
        selected_reason = None
        selected_traders: list[str] = []
        selected_ttl = 0

        if full_interval > 0 and minute % full_interval == 0:
            selected_reason = "full"
            selected_traders = list(MOEX_TRADERS)
            selected_ttl = full_ttl
        elif event_interval > 0 and minute % event_interval == 0:
            event_accumulator += max(0.0, min(1.0, event_fraction))
            if event_accumulator >= 1.0:
                event_accumulator -= 1.0
                selected_reason = "event"
                selected_traders = list(EVENT_TRADERS)
                selected_ttl = event_ttl
        elif fast_interval > 0 and minute % fast_interval == 0:
            selected_reason = "fast"
            selected_traders = list(FAST_TRADERS)
            selected_ttl = fast_ttl

        if not selected_reason:
            continue
        if pending:
            skipped[selected_reason] += 1
            continue

        due = [
            trader
            for trader in selected_traders
            if effective_due(last_created[trader], minute, selected_ttl)
        ]
        if not due:
            no_due[selected_reason] += 1
            continue

        for trader in due:
            last_created[trader] = minute

        job_count = len(due)
        jobs += job_count
        waves[selected_reason] += 1
        wave_jobs.append(job_count)

        worker_rounds = math.ceil(job_count / max(1, max_workers))
        worker_minutes = worker_rounds * (job_seconds / 60.0)
        starter_jobs_per_minute = max(1, dispatch_ticks * start_batch)
        starter_minutes = max(0.0, (job_count - 1) / starter_jobs_per_minute)
        drain_minutes = max(worker_minutes, starter_minutes)
        busy_until_minute = minute + max(1, math.ceil(drain_minutes))

    hours = minutes / 60.0
    return {
        "jobs_per_hour": jobs / hours,
        "waves_per_hour": {key: waves[key] / hours for key in ("full", "event", "fast")},
        "skipped_per_hour": sum(skipped.values()) / hours,
        "skipped_by_reason": {key: skipped[key] / hours for key in ("full", "event", "fast")},
        "no_due_per_hour": sum(no_due.values()) / hours,
        "avg_jobs_per_wave": mean(wave_jobs) if wave_jobs else 0.0,
    }


def verdict(utilization: float, calls_per_hour: float, call_limit: int, skipped_per_hour: float) -> tuple[str, str]:
    if call_limit > 0 and calls_per_hour > call_limit:
        return "OVERLOAD", "AI hourly limit"
    if utilization > 0.90:
        return "OVERLOAD", "worker pool"
    if skipped_per_hour > 2.0:
        return "HOT", "waves often skipped"
    if call_limit > 0 and calls_per_hour > call_limit * 0.85:
        return "HOT", "near AI limit"
    if utilization > 0.70:
        return "HOT", "near worker capacity"
    return "OK", "capacity margin"


def build_report(args) -> dict:
    window_minutes = max(1, int(args.hours * 60))
    with connect() as conn:
        ensure_job_schema(conn)
        ensure_ai_call_schema(conn)
        ensure_dispatcher_schema(conn)
        jobs = fetch_jobs(conn, window_minutes)
        calls = fetch_calls(conn, window_minutes)
        dispatcher_rows = fetch_dispatcher_rows(conn, window_minutes)
        active_cooldowns = fetch_active_cooldowns(conn)

    job_statuses = Counter(row["status"] for row in jobs)
    call_statuses = Counter(row["status"] for row in calls)
    durations = [row["duration_seconds"] for row in jobs if row["duration_seconds"] is not None]
    queue_delays = [row["queue_delay_seconds"] for row in jobs if row["queue_delay_seconds"] is not None]
    call_durations = [row["duration_seconds"] for row in calls if row["duration_seconds"] is not None]
    prompt_chars = [row["prompt_chars"] for row in calls]
    started_jobs = sum(1 for row in jobs if row["status"] != "queued")
    external_requests = [
        row
        for row in calls
        if row["request_allowed"] and row["status"] not in {"model_skipped", "budget_blocked"}
    ]
    logged_rows_per_started_job = len(calls) / started_jobs if started_jobs else 1.0
    external_requests_per_started_job = len(external_requests) / started_jobs if started_jobs else 1.0
    requests_per_job = args.requests_per_job if args.requests_per_job is not None else external_requests_per_started_job
    failures = sum(call_statuses[status] for status in ("exhausted", "timeout", "error", "parse_error", "budget_blocked"))
    blocked = sum(1 for row in calls if not row["request_allowed"])
    event_fraction, event_fraction_source = event_active_fraction(dispatcher_rows)

    p90_duration = percentile(durations, 0.90) or percentile(call_durations, 0.90) or DEFAULT_JOB_SECONDS
    p50_duration = percentile(durations, 0.50)
    p90_queue = percentile(queue_delays, 0.90)
    worker_capacity_jobs_hour = args.max_workers * 3600.0 / max(1.0, p90_duration)
    starter_capacity_jobs_hour = max(1, args.dispatch_ticks * args.start_batch) * 60.0
    capacity_jobs_hour = min(worker_capacity_jobs_hour, starter_capacity_jobs_hour)

    simulations = []
    for full_interval in args.full_intervals:
        for fast_interval in args.fast_intervals:
            for event_interval in args.event_intervals:
                sim = simulate_schedule(
                    full_interval=full_interval,
                    fast_interval=fast_interval,
                    event_interval=event_interval,
                    full_ttl=args.full_ttl,
                    fast_ttl=args.fast_ttl,
                    event_ttl=args.event_ttl,
                    max_workers=args.max_workers,
                    start_batch=args.start_batch,
                    dispatch_ticks=args.dispatch_ticks,
                    job_seconds=p90_duration,
                    event_fraction=event_fraction,
                )
                calls_per_hour = sim["jobs_per_hour"] * max(1.0, requests_per_job)
                utilization = sim["jobs_per_hour"] / max(1.0, capacity_jobs_hour)
                state, reason = verdict(utilization, calls_per_hour, args.trader_hourly_limit, sim["skipped_per_hour"])
                simulations.append({
                    "full_interval_min": full_interval,
                    "fast_interval_min": fast_interval,
                    "event_interval_min": event_interval,
                    "jobs_per_hour": sim["jobs_per_hour"],
                    "calls_per_hour": calls_per_hour,
                    "capacity_jobs_per_hour": capacity_jobs_hour,
                    "utilization": utilization,
                    "skipped_waves_per_hour": sim["skipped_per_hour"],
                    "waves_per_hour": sim["waves_per_hour"],
                    "status": state,
                    "reason": reason,
                })

    status_rank = {"OK": 0, "HOT": 1, "OVERLOAD": 2}
    simulations.sort(
        key=lambda row: (
            status_rank[row["status"]],
            row["fast_interval_min"],
            row["full_interval_min"],
            row["event_interval_min"],
            -row["jobs_per_hour"],
        )
    )

    dispatcher_decisions = Counter(row["decision"] for row in dispatcher_rows)
    dispatcher_waves = Counter(row["wave_reason"] for row in dispatcher_rows if row["wave_reason"])
    generated_at = datetime.now(timezone.utc).astimezone(TZ).isoformat(timespec="seconds")

    return {
        "generated_at": generated_at,
        "window_hours": args.hours,
        "observed": {
            "jobs": {
                "total": len(jobs),
                "statuses": dict(job_statuses),
                "duration_p50_sec": p50_duration,
                "duration_p90_sec": p90_duration,
                "queue_delay_p90_sec": p90_queue,
            },
            "ai_calls": {
                "total": len(calls),
                "statuses": dict(call_statuses),
                "failures": failures,
                "blocked": blocked,
                "logged_rows": len(calls),
                "external_requests": len(external_requests),
                "logged_rows_per_started_job": logged_rows_per_started_job,
                "external_requests_per_started_job": external_requests_per_started_job,
                "simulation_requests_per_job": requests_per_job,
                "prompt_avg_chars": mean(prompt_chars) if prompt_chars else 0,
                "prompt_max_chars": max(prompt_chars) if prompt_chars else 0,
            },
            "dispatcher": {
                "rows": len(dispatcher_rows),
                "decisions": dict(dispatcher_decisions),
                "waves": dict(dispatcher_waves),
                "event_active_fraction": event_fraction,
                "event_active_fraction_source": event_fraction_source,
            },
            "model_cooldowns": {
                "active": active_cooldowns,
            },
        },
        "capacity": {
            "max_workers": args.max_workers,
            "start_batch": args.start_batch,
            "dispatch_ticks": args.dispatch_ticks,
            "p90_job_seconds": p90_duration,
            "jobs_per_hour": capacity_jobs_hour,
            "trader_ai_calls_per_hour_limit": args.trader_hourly_limit,
        },
        "simulations": simulations,
    }


def print_report(report: dict, limit: int) -> None:
    observed = report["observed"]
    capacity = report["capacity"]
    print(f"AI dispatcher interval analysis at {report['generated_at']}")
    print(f"Window: {report['window_hours']}h")
    print()
    print("Observed")
    print(f"- jobs: {observed['jobs']['total']} {observed['jobs']['statuses']}")
    print(
        "- duration: "
        f"p50={fmt_num(observed['jobs']['duration_p50_sec'])}s, "
        f"p90={fmt_num(observed['jobs']['duration_p90_sec'])}s, "
        f"queue_p90={fmt_num(observed['jobs']['queue_delay_p90_sec'])}s"
    )
    print(
        "- ai calls: "
        f"{observed['ai_calls']['total']} {observed['ai_calls']['statuses']}, "
        f"external_requests={observed['ai_calls']['external_requests']}, "
        f"failures={observed['ai_calls']['failures']}, "
        f"blocked={observed['ai_calls']['blocked']}, "
        f"rows/job={fmt_num(observed['ai_calls']['logged_rows_per_started_job'], 2)}, "
        f"requests/job={fmt_num(observed['ai_calls']['simulation_requests_per_job'], 2)}, "
        f"prompt_avg={fmt_num(observed['ai_calls']['prompt_avg_chars'], 0)}, "
        f"prompt_max={observed['ai_calls']['prompt_max_chars']}"
    )
    print(
        "- dispatcher: "
        f"rows={observed['dispatcher']['rows']}, "
        f"decisions={observed['dispatcher']['decisions']}, "
        f"waves={observed['dispatcher']['waves']}, "
        f"event_active={fmt_num(observed['dispatcher']['event_active_fraction'] * 100, 0)}% "
        f"({observed['dispatcher']['event_active_fraction_source']})"
    )
    cooldowns = observed.get("model_cooldowns", {}).get("active", [])
    if cooldowns:
        compact = [
            f"{row['category']}:{row['model_id']} until {row['unavailable_until']} ({row['failure_status']})"
            for row in cooldowns[:8]
        ]
        suffix = "" if len(cooldowns) <= 8 else f", +{len(cooldowns) - 8} more"
        print(f"- active model cooldowns: {len(cooldowns)}; " + "; ".join(compact) + suffix)
    else:
        print("- active model cooldowns: 0")
    print()
    print(
        "Capacity model: "
        f"workers={capacity['max_workers']}, "
        f"start_batch={capacity['start_batch']}, "
        f"ticks/min={capacity['dispatch_ticks']}, "
        f"capacity={fmt_num(capacity['jobs_per_hour'])} jobs/h, "
        f"AI limit={capacity['trader_ai_calls_per_hour_limit']} calls/h"
    )
    print()
    print("Scenario table")
    print("status    full fast event jobs/h calls/h util skipped/h reason")
    for row in report["simulations"][:limit]:
        print(
            f"{row['status']:<9} "
            f"{row['full_interval_min']:>4} "
            f"{row['fast_interval_min']:>4} "
            f"{row['event_interval_min']:>5} "
            f"{fmt_num(row['jobs_per_hour']):>6} "
            f"{fmt_num(row['calls_per_hour']):>7} "
            f"{fmt_num(row['utilization'] * 100, 0):>4}% "
            f"{fmt_num(row['skipped_waves_per_hour']):>9} "
            f"{row['reason']}"
        )

    ok_rows = [row for row in report["simulations"] if row["status"] == "OK"]
    hot_rows = [row for row in report["simulations"] if row["status"] == "HOT"]
    chosen = ok_rows[0] if ok_rows else (hot_rows[0] if hot_rows else report["simulations"][0])
    print()
    print(
        "Recommended current candidate: "
        f"full={chosen['full_interval_min']}m, "
        f"fast={chosen['fast_interval_min']}m, "
        f"event={chosen['event_interval_min']}m "
        f"({chosen['status']}: {chosen['reason']}, "
        f"{fmt_num(chosen['calls_per_hour'])} calls/h)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze MOEX AI dispatcher logs and simulate launch intervals.")
    parser.add_argument("--hours", type=float, default=float(os.getenv("AI_INTERVAL_ANALYZER_HOURS", "6")))
    parser.add_argument("--full-intervals", type=parse_csv_ints, default=parse_csv_ints(os.getenv("AI_INTERVAL_FULL_INTERVALS", "15,20,30,45,60,90")))
    parser.add_argument("--fast-intervals", type=parse_csv_ints, default=parse_csv_ints(os.getenv("AI_INTERVAL_FAST_INTERVALS", "5,10,15,20,30")))
    parser.add_argument("--event-intervals", type=parse_csv_ints, default=parse_csv_ints(os.getenv("AI_INTERVAL_EVENT_INTERVALS", "5,10,15,20,30")))
    parser.add_argument("--full-ttl", type=int, default=int(os.getenv("AI_JOB_FULL_TRADER_TTL_MINUTES", os.getenv("AI_JOB_MIN_TRADER_TTL_MINUTES", "20"))))
    parser.add_argument("--fast-ttl", type=int, default=int(os.getenv("AI_JOB_FAST_TRADER_TTL_MINUTES", "8")))
    parser.add_argument("--event-ttl", type=int, default=int(os.getenv("AI_JOB_EVENT_TRADER_TTL_MINUTES", "5")))
    parser.add_argument("--max-workers", type=int, default=int(os.getenv("AI_JOB_MAX_WORKERS", "2")))
    parser.add_argument("--start-batch", type=int, default=int(os.getenv("AI_JOB_START_BATCH", "1")))
    parser.add_argument("--dispatch-ticks", type=int, default=int(os.getenv("AI_JOB_DISPATCH_TICKS", "3")))
    parser.add_argument("--trader-hourly-limit", type=int, default=hourly_limit("trader"))
    parser.add_argument("--requests-per-job", type=float, default=None, help="Override observed external AI requests per started trader job for simulation.")
    parser.add_argument("--limit", type=int, default=int(os.getenv("AI_INTERVAL_ANALYZER_PRINT_LIMIT", "20")))
    parser.add_argument("--json", action="store_true", help="Print full report as JSON.")
    args = parser.parse_args()

    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, args.limit)


if __name__ == "__main__":
    main()
