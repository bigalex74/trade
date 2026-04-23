#!/usr/bin/env python3
"""Публикует компактный внутридневной дайджест MOEX в трейдерскую ALGO KB."""

from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from algo_kb_client import insert_text_to_algo_kb
from hybrid_rag import infer_news_secids, load_instrument_match_terms, load_news_rows
from market_regime import compact_regime, latest_market_regime, refresh_market_regime
from market_research_context import get_db_connection, load_market_context


MOSCOW_TZ = ZoneInfo("Europe/Moscow")
FOCUS_SECIDS = ("SBER", "GAZP", "LKOH", "ROSN", "MOEX", "AFLT", "GMKN", "NVTK", "TATN")


def _fmt_pct(value) -> str:
    if value is None:
        return "н/д"
    return f"{float(value):+.2f}%"


def _fmt_price(value) -> str:
    if value is None:
        return "н/д"
    return f"{float(value):.4g}"


def _window_value(item: dict, window_name: str, field: str):
    return (((item or {}).get("windows") or {}).get(window_name) or {}).get(field)


def _day_value_mrub(item: dict) -> float:
    value = _window_value(item, "current_day", "value")
    return round(float(value or 0) / 1_000_000, 2)


def _metric(item: tuple[str, dict], key: str) -> float:
    return float((item[1] or {}).get(key) or 0)


def _line_for_symbol(secid: str, payload: dict, *, include_liquidity: bool = True) -> str:
    parts = [
        f"{secid}",
        f"p={_fmt_price(payload.get('price'))}",
        f"d={_fmt_pct(payload.get('day_change'))}",
        f"h={_fmt_pct(payload.get('hour_change'))}",
        f"5м={_fmt_pct(payload.get('five_min_change'))}",
    ]
    if include_liquidity:
        parts.append(f"val={_day_value_mrub(payload)}м")
    return "- " + " ".join(parts)


def _load_sentiment(conn, secids: list[str]) -> dict[str, dict]:
    if not secids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT secid, score, summary, updated_at
            FROM analytics.market_sentiment
            WHERE secid = ANY(%s)
            """,
            (secids,),
        )
        return {
            row[0]: {
                "score": float(row[1]) if row[1] is not None else None,
                "summary": row[2],
                "updated_at": row[3].isoformat() if row[3] else None,
            }
            for row in cur.fetchall()
        }


def _fresh_regime(conn) -> dict:
    regime = latest_market_regime(conn, max_age_minutes=180)
    if regime:
        return compact_regime(regime)
    return compact_regime(refresh_market_regime(conn, dry_run=True))


def _recent_news_lines(conn, *, hours: int, limit: int) -> list[str]:
    rows = load_news_rows(conn, lookback_hours=hours, limit=limit)
    terms = load_instrument_match_terms(conn)
    lines = []
    for row in rows:
        secids, sources, matched_terms = infer_news_secids(row, terms)
        title = " ".join(str(row.get("title") or "").split())
        summary = " ".join(str(row.get("summary") or row.get("content") or "").split())
        if not title and not summary:
            continue
        tag = ",".join(secids) if secids else "общий рынок"
        source = "+".join(sources) if sources else "без тикера"
        headline = title or summary
        term_note = f" key={','.join(matched_terms[:2])}" if matched_terms else ""
        lines.append(f"- {tag}: {headline[:120]} (match={source}{term_note})")
        if len(lines) >= limit:
            break
    return lines


def build_digest(*, top: int = 3, news_hours: int = 24, news_limit: int = 3, focus_limit: int = 8) -> str:
    conn = get_db_connection()
    try:
        context = load_market_context(conn)
        if len(context) < 5:
            raise RuntimeError(f"Market context is too small for intraday digest: {len(context)} instruments")

        now_msk = datetime.now(MOSCOW_TZ)
        latest_update = max(
            (payload.get("updated_at") for payload in context.values() if payload.get("updated_at")),
            default="unknown",
        )
        regime = _fresh_regime(conn)
        by_day = sorted(context.items(), key=lambda item: _metric(item, "day_change"))
        by_hour = sorted(context.items(), key=lambda item: _metric(item, "hour_change"), reverse=True)
        by_liquidity = sorted(context.items(), key=lambda item: _day_value_mrub(item[1]), reverse=True)
        focus = [secid for secid in FOCUS_SECIDS if secid in context and context[secid].get("price") is not None]
        focus = focus[:focus_limit]
        sentiment = _load_sentiment(conn, focus)
        news_lines = _recent_news_lines(conn, hours=news_hours, limit=news_limit)

        lines = [
            f"MOEX INTRADAY DIGEST ДЛЯ ТРЕЙДЕРОВ ({now_msk.strftime('%Y-%m-%d %H:%M MSK')})",
            f"Свежесть: {latest_update}. Инструментов: {len(context)}.",
            (
                "Режим: "
                f"{regime.get('regime', 'н/д')} risk={regime.get('risk', 'н/д')} "
                f"breadth={regime.get('breadth', 'н/д')}% "
                f"d={_fmt_pct(regime.get('day'))} h={_fmt_pct(regime.get('hour'))}."
            ),
            "",
            "Рост за день:",
        ]
        lines.extend(_line_for_symbol(secid, payload) for secid, payload in reversed(by_day[-top:]))
        lines.extend(["", "Снижение за день:"])
        lines.extend(_line_for_symbol(secid, payload) for secid, payload in by_day[:top])
        lines.extend(["", "Движение за час:"])
        lines.extend(_line_for_symbol(secid, payload) for secid, payload in by_hour[:top])
        lines.extend(["", "Ликвидность дня:"])
        lines.extend(_line_for_symbol(secid, payload) for secid, payload in by_liquidity[:top])
        lines.extend(["", "Фокус:"])
        for secid in focus:
            line = _line_for_symbol(secid, context[secid])
            sent = sentiment.get(secid)
            if sent:
                line += f" sent={sent['score']}"
            lines.append(line)
        lines.extend(["", f"Новости {news_hours}ч:"])
        lines.extend(news_lines or ["- Релевантных свежих новостей не найдено."])
        lines.extend(
            [
                "",
                "Правило: контекст риска и рынка, не самостоятельный торговый сигнал.",
            ]
        )
        return "\n".join(lines)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Публикует внутридневной MOEX digest в ALGO KB.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--news-hours", type=int, default=24)
    parser.add_argument("--news-limit", type=int, default=3)
    parser.add_argument("--focus-limit", type=int, default=8)
    args = parser.parse_args()

    digest = build_digest(
        top=args.top,
        news_hours=args.news_hours,
        news_limit=args.news_limit,
        focus_limit=args.focus_limit,
    )
    if args.dry_run:
        print(digest)
        return 0

    now_msk = datetime.now(MOSCOW_TZ)
    insert_text_to_algo_kb(
        digest,
        file_source=f"moex_intraday_digest_{now_msk.strftime('%Y-%m-%d_%H%M')}.txt",
        log_func=print,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
