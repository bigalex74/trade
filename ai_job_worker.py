#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time

from ai_job_store import connect, decode_command, ensure_schema


def update_job(conn, job_id, status, exit_code=None, error=None, duration=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE trading.ai_jobs
            SET status = %s,
                exit_code = %s,
                error = %s,
                duration_seconds = %s,
                finished_at = clock_timestamp(),
                heartbeat_at = clock_timestamp(),
                updated_at = clock_timestamp()
            WHERE id = %s
            """,
            (status, exit_code, error, duration, job_id),
        )
    conn.commit()


def terminate_process_group(pid):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return
        time.sleep(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: ai_job_worker.py JOB_ID", file=sys.stderr)
        return 2

    job_id = int(sys.argv[1])
    conn = connect()
    ensure_schema(conn)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT command, log_path
            FROM trading.ai_jobs
            WHERE id = %s AND status = 'running'
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if not row:
        conn.close()
        return 0

    command = decode_command(row[0])
    log_path = row[1] or "/home/user/logs/ai_jobs.log"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    started = time.monotonic()
    try:
        with open(log_path, "a") as log:
            log.write(f"[ {time.strftime('%Y-%m-%d %H:%M:%S')} ] AI job {job_id} started: {' '.join(command)}\n")
            log.flush()
            proc = subprocess.Popen(command, stdout=log, stderr=log, text=True, start_new_session=True)
            returncode = proc.wait()
            terminate_process_group(proc.pid)
            duration = round(time.monotonic() - started, 3)
            status = "succeeded" if returncode == 0 else "failed"
            log.write(f"[ {time.strftime('%Y-%m-%d %H:%M:%S')} ] AI job {job_id} finished: status={status} exit={returncode} duration={duration}s\n")
        update_job(conn, job_id, status, exit_code=returncode, duration=duration)
        return returncode
    except Exception as exc:
        duration = round(time.monotonic() - started, 3)
        update_job(conn, job_id, "failed", exit_code=255, error=f"{type(exc).__name__}: {exc}", duration=duration)
        return 255
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
