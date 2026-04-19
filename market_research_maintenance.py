#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg2


DB_CONFIG = {
    "host": "localhost",
    "database": "market_research",
    "user": "n8n_user",
    "password": "n8n_db_password",
}

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UTC = timezone.utc
INTRADAY_INTERVALS = ("1m", "1h")


@dataclass(frozen=True)
class HealthIssue:
    level: str
    message: str


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def current_moscow_day_start_utc(reference_dt: datetime | None = None):
    current_local = (reference_dt or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    local_day_start = datetime.combine(current_local.date(), time.min, tzinfo=MOSCOW_TZ)
    return local_day_start.astimezone(UTC)


def cleanup_intraday_history(dry_run: bool):
    cutoff_utc = current_moscow_day_start_utc()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT interval_name, count(*)
                FROM raw.candle
                WHERE interval_name = ANY(%s)
                  AND candle_time < %s
                GROUP BY interval_name
                ORDER BY interval_name
                """,
                (list(INTRADAY_INTERVALS), cutoff_utc),
            )
            to_delete = {interval_name: count for interval_name, count in cur.fetchall()}

            if dry_run:
                print(
                    json.dumps(
                        {
                            "mode": "dry-run",
                            "cutoff_utc": cutoff_utc.isoformat(),
                            "rows_to_delete": to_delete,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0

            cur.execute(
                """
                DELETE FROM raw.candle
                WHERE interval_name = ANY(%s)
                  AND candle_time < %s
                """,
                (list(INTRADAY_INTERVALS), cutoff_utc),
            )
            deleted_rows = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "mode": "delete",
                "cutoff_utc": cutoff_utc.isoformat(),
                "rows_to_delete_by_interval": to_delete,
                "deleted_rows_total": deleted_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_health_snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ref.instrument
            WHERE active = TRUE
            """
        )
        active_instruments = cur.fetchone()[0]

        cur.execute(
            """
            SELECT interval_name, max(candle_time)
            FROM raw.candle
            WHERE interval_name IN ('1m', '1h', '1d', '1w')
            GROUP BY interval_name
            """
        )
        interval_latest = {interval_name: ts for interval_name, ts in cur.fetchall()}

        cur.execute(
            """
            SELECT
                count(*) AS context_rows,
                count(*) FILTER (WHERE current_price IS NOT NULL) AS priced_rows,
                max(updated_at) AS latest_context_update
            FROM analytics.trader_market_context_v
            WHERE active = TRUE
            """
        )
        context_rows, priced_rows, latest_context_update = cur.fetchone()

    return {
        "active_instruments": active_instruments,
        "interval_latest": interval_latest,
        "context_rows": context_rows,
        "priced_rows": priced_rows,
        "latest_context_update": latest_context_update,
    }


def evaluate_health(snapshot):
    now_local = datetime.now(MOSCOW_TZ)
    now_utc = now_local.astimezone(UTC)
    issues: list[HealthIssue] = []

    active_instruments = snapshot["active_instruments"]
    context_rows = snapshot["context_rows"] or 0
    priced_rows = snapshot["priced_rows"] or 0
    latest_context_update = snapshot["latest_context_update"]
    interval_latest = snapshot["interval_latest"]

    if context_rows < active_instruments:
        issues.append(
            HealthIssue(
                "error",
                f"context rows {context_rows} меньше active instruments {active_instruments}",
            )
        )

    min_priced_rows = max(20, active_instruments - 4)
    if priced_rows < min_priced_rows:
        issues.append(
            HealthIssue(
                "error",
                f"priced rows {priced_rows} меньше ожидаемого минимума {min_priced_rows}",
            )
        )

    if latest_context_update is None:
        issues.append(HealthIssue("error", "context не обновлялся ни разу"))
    else:
        context_age = now_utc - latest_context_update.astimezone(UTC)
        context_limit = timedelta(minutes=45) if now_local.weekday() < 5 and 10 <= now_local.hour <= 23 else timedelta(hours=18)
        if context_age > context_limit:
            issues.append(
                HealthIssue(
                    "error",
                    f"context stale: возраст {context_age} больше лимита {context_limit}",
                )
            )

    latest_1d = interval_latest.get("1d")
    if latest_1d is None:
        issues.append(HealthIssue("error", "в raw.candle отсутствует интервал 1d"))
    else:
        age_1d = now_utc - latest_1d.astimezone(UTC)
        if age_1d > timedelta(days=7):
            issues.append(
                HealthIssue(
                    "error",
                    f"1d stale: возраст {age_1d} больше лимита 7 дней",
                )
            )

    in_weekday_session = now_local.weekday() < 5 and 10 <= now_local.hour <= 23
    if in_weekday_session:
        latest_1m = interval_latest.get("1m")
        latest_1h = interval_latest.get("1h")

        if latest_1m is None:
            issues.append(HealthIssue("error", "в raw.candle отсутствует интервал 1m в торговую сессию"))
        else:
            age_1m = now_utc - latest_1m.astimezone(UTC)
            if age_1m > timedelta(minutes=25):
                issues.append(
                    HealthIssue(
                        "error",
                        f"1m stale: возраст {age_1m} больше лимита 25 минут",
                    )
                )

        if latest_1h is None:
            issues.append(HealthIssue("error", "в raw.candle отсутствует интервал 1h в торговую сессию"))
        else:
            age_1h = now_utc - latest_1h.astimezone(UTC)
            if age_1h > timedelta(hours=3):
                issues.append(
                    HealthIssue(
                        "error",
                        f"1h stale: возраст {age_1h} больше лимита 3 часа",
                    )
                )

    return issues


def run_health_check(json_output: bool):
    conn = get_connection()
    try:
        snapshot = load_health_snapshot(conn)
    finally:
        conn.close()

    issues = evaluate_health(snapshot)
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "active_instruments": snapshot["active_instruments"],
        "context_rows": snapshot["context_rows"],
        "priced_rows": snapshot["priced_rows"],
        "latest_context_update": snapshot["latest_context_update"].isoformat() if snapshot["latest_context_update"] else None,
        "interval_latest": {
            key: value.isoformat() if value else None
            for key, value in snapshot["interval_latest"].items()
        },
        "issues": [{"level": issue.level, "message": issue.message} for issue in issues],
        "status": "ok" if not issues else "error",
    }

    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[health-check] status={payload['status']}")
        print(f"active_instruments={payload['active_instruments']} context_rows={payload['context_rows']} priced_rows={payload['priced_rows']}")
        print(f"latest_context_update={payload['latest_context_update']}")
        for interval_name in ("1m", "1h", "1d", "1w"):
            print(f"{interval_name}_latest={payload['interval_latest'].get(interval_name)}")
        if issues:
            print("issues:")
            for issue in issues:
                print(f"- {issue.level}: {issue.message}")

    return 0 if not issues else 1


def build_parser():
    parser = argparse.ArgumentParser(description="Market research maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cleanup_parser = subparsers.add_parser(
        "cleanup-intraday-history",
        help="Delete previous-day intraday candles from raw.candle",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many rows would be deleted without applying changes",
    )

    health_parser = subparsers.add_parser(
        "health-check",
        help="Check freshness and completeness of trader context and candle feeds",
    )
    health_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "cleanup-intraday-history":
        raise SystemExit(cleanup_intraday_history(dry_run=args.dry_run))
    if args.command == "health-check":
        raise SystemExit(run_health_check(json_output=args.json))

    parser.error("Unsupported command")


if __name__ == "__main__":
    main()
