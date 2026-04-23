#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

import psycopg2.extras

from strategy_candidate_pipeline import ensure_schema, get_db_connection


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def evaluate_candidate(conn, candidate_id: int, run_id: int | None, min_return_pct: float, max_drawdown_pct: float) -> dict[str, Any]:
    ensure_schema(conn)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM trading.strategy_candidates WHERE id = %s", (candidate_id,))
        candidate = cur.fetchone()
        if not candidate:
            return {"candidate_id": candidate_id, "allowed": False, "reason": "candidate_not_found"}

        if run_id is None:
            run_id = candidate.get("backtest_run_id")
        if run_id is None:
            return {"candidate_id": candidate_id, "allowed": False, "reason": "backtest_required"}

        cur.execute("SELECT * FROM trading.ai_backtest_runs WHERE id = %s", (run_id,))
        run = cur.fetchone()
        if not run:
            return {"candidate_id": candidate_id, "run_id": run_id, "allowed": False, "reason": "backtest_run_not_found"}
        if run["status"] != "succeeded":
            return {"candidate_id": candidate_id, "run_id": run_id, "allowed": False, "reason": f"backtest_status:{run['status']}"}

        return_pct = _float(run["return_pct"])
        drawdown_pct = _float(run["max_drawdown_pct"])
        if return_pct < min_return_pct:
            return {
                "candidate_id": candidate_id,
                "run_id": run_id,
                "allowed": False,
                "reason": f"return_below_threshold:{return_pct:.3f}<{min_return_pct:.3f}",
                "return_pct": return_pct,
                "max_drawdown_pct": drawdown_pct,
            }
        if drawdown_pct < max_drawdown_pct:
            return {
                "candidate_id": candidate_id,
                "run_id": run_id,
                "allowed": False,
                "reason": f"drawdown_below_threshold:{drawdown_pct:.3f}<{max_drawdown_pct:.3f}",
                "return_pct": return_pct,
                "max_drawdown_pct": drawdown_pct,
            }
        return {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "allowed": True,
            "reason": "backtest_gate_passed",
            "return_pct": return_pct,
            "max_drawdown_pct": drawdown_pct,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate strategy candidate promotion against saved backtest results.")
    parser.add_argument("--candidate-id", type=int, required=True)
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--min-return-pct", type=float, default=0.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=-10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        result = evaluate_candidate(conn, args.candidate_id, args.run_id, args.min_return_pct, args.max_drawdown_pct)
        if not args.dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trading.strategy_candidates
                    SET validation_status = %s,
                        status = CASE WHEN %s THEN 'BACKTEST_PASSED' ELSE status END,
                        backtest_run_id = COALESCE(%s, backtest_run_id),
                        metadata = metadata || %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        "PASSED" if result["allowed"] else "BLOCKED",
                        result["allowed"],
                        args.run_id,
                        json.dumps({"release_gate": result}),
                        args.candidate_id,
                    ),
                )
            conn.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
