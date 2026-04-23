#!/usr/bin/env python3
"""Publish a concise MOEX market snapshot into the ALGO knowledge base."""

from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from algo_kb_client import insert_text_to_algo_kb
from market_research_context import load_market_context


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _fmt_pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+.2f}%"


def _fmt_price(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.4g}"


def _sort_change(item):
    secid, payload = item
    change = payload.get("day_change")
    if change is None:
        change = payload.get("change")
    return float(change or 0.0), secid


def build_summary(top: int = 8) -> str:
    context = load_market_context()
    if len(context) < 5:
        raise RuntimeError(f"Market context is too small for ALGO KB summary: {len(context)} instruments")

    now_msk = datetime.now(MOSCOW_TZ)
    sorted_items = sorted(context.items(), key=_sort_change)
    losers = sorted_items[:top]
    gainers = list(reversed(sorted_items[-top:]))

    groups = {}
    for payload in context.values():
        group = payload.get("instrument_group") or "unknown"
        groups[group] = groups.get(group, 0) + 1

    updated_values = [payload.get("updated_at") for payload in context.values() if payload.get("updated_at")]
    latest_update = max(updated_values) if updated_values else "unknown"

    lines = [
        f"MOEX MARKET SUMMARY FOR TRADING AGENTS ({now_msk.strftime('%Y-%m-%d %H:%M MSK')})",
        f"Universe size: {len(context)} active instruments.",
        "Instrument groups: " + ", ".join(f"{name}={count}" for name, count in sorted(groups.items())),
        f"Latest market context update: {latest_update}.",
        "",
        "Top gainers by current day change:",
    ]

    for secid, payload in gainers:
        lines.append(
            f"- {secid}: price={_fmt_price(payload.get('price'))}, "
            f"day={_fmt_pct(payload.get('day_change'))}, hour={_fmt_pct(payload.get('hour_change'))}, "
            f"issuer={payload.get('issuer_name') or 'n/a'}"
        )

    lines.extend(["", "Top losers by current day change:"])
    for secid, payload in losers:
        lines.append(
            f"- {secid}: price={_fmt_price(payload.get('price'))}, "
            f"day={_fmt_pct(payload.get('day_change'))}, hour={_fmt_pct(payload.get('hour_change'))}, "
            f"issuer={payload.get('issuer_name') or 'n/a'}"
        )

    focus = ["SBER", "GAZP", "LKOH", "ROSN", "MOEX", "YNDX", "USD000UTSTOM", "GLDRUB_TOM"]
    lines.extend(["", "Focus instruments:"])
    for secid in focus:
        payload = context.get(secid)
        if not payload:
            continue
        lines.append(
            f"- {secid}: price={_fmt_price(payload.get('price'))}, "
            f"day={_fmt_pct(payload.get('day_change'))}, "
            f"5m={_fmt_pct(payload.get('five_min_change'))}, "
            f"group={payload.get('instrument_group') or 'n/a'}"
        )

    lines.extend(
        [
            "",
            "Use this as compact daily market context. Do not treat it as a trade signal by itself.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    summary = build_summary(top=args.top)
    if args.dry_run:
        print(summary)
        return 0

    now_msk = datetime.now(MOSCOW_TZ)
    insert_text_to_algo_kb(
        summary,
        file_source=f"moex_market_summary_{now_msk.strftime('%Y-%m-%d_%H%M')}.txt",
        log_func=print,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
