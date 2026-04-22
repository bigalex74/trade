import json
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras


DB_CONFIG = {
    "host": os.getenv("AI_JOBS_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("AI_JOBS_DB_NAME", "market_research"),
    "user": os.getenv("AI_JOBS_DB_USER", os.getenv("DB_USER", "n8n_user")),
    "password": os.getenv("AI_JOBS_DB_PASSWORD", os.getenv("DB_PASSWORD", "n8n_db_password")),
}


DDL = """
CREATE TABLE IF NOT EXISTS trading.ai_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    market TEXT NOT NULL,
    job_type TEXT NOT NULL,
    trader_name TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    command JSONB NOT NULL,
    log_path TEXT,
    scheduled_for TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    exit_code INTEGER,
    duration_seconds NUMERIC,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', 'stale'))
);
CREATE INDEX IF NOT EXISTS ai_jobs_status_priority_idx
    ON trading.ai_jobs (status, priority DESC, scheduled_for, id);
CREATE INDEX IF NOT EXISTS ai_jobs_market_created_idx
    ON trading.ai_jobs (market, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_jobs_running_idx
    ON trading.ai_jobs (started_at)
    WHERE status = 'running';
"""


def connect():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn=None):
    own_conn = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def now_utc():
    return datetime.now(timezone.utc)


def encode_command(command):
    return psycopg2.extras.Json(list(command))


def decode_command(command):
    if isinstance(command, str):
        return json.loads(command)
    return command
