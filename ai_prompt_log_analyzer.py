#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import mean

from ai_job_store import connect


MARKERS = [
    "KB:",
    "DNA:",
    "Cash:",
    "Portfolio:",
    "History:",
    "REGIME:",
    "META_CONSENSUS:",
    "MARKET_FEATURES:",
    "MANDATE:",
    "Respond ONLY raw JSON:",
]

GENERIC_KB_MARKERS = (
    "strategic alpha refers",
    "understanding strategic alpha",
    "to provide a comprehensive overview",
    "it is important to assess",
    "we can analyze relevant concepts",
    "excess return of an investment",
    "можно обсудить общие уроки",
)


def percentile(values, pct):
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    idx = round((len(clean) - 1) * pct)
    return clean[idx]


def section(prompt: str, marker: str) -> str:
    start = prompt.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    ends = [prompt.find(next_marker, start) for next_marker in MARKERS if prompt.find(next_marker, start) >= 0]
    end = min(ends) if ends else len(prompt)
    return prompt[start:end].strip(" .")


def section_lengths(prompt: str) -> dict[str, int]:
    lengths = {}
    first_positions = [prompt.find(marker) for marker in MARKERS if prompt.find(marker) >= 0]
    lengths["prefix"] = min(first_positions) if first_positions else len(prompt)
    for marker in MARKERS:
        value = section(prompt, marker)
        if value:
            lengths[marker.rstrip(":")] = len(value)
    return lengths


def is_generic_kb(kb: str) -> bool:
    lower = (kb or "").lower()
    return any(marker in lower for marker in GENERIC_KB_MARKERS)


def parse_market_features(prompt: str):
    value = section(prompt, "MARKET_FEATURES:")
    if not value:
        return None, "missing"
    try:
        return json.loads(value), None
    except Exception as exc:
        return None, type(exc).__name__


def fetch_rows(hours: float, category: str):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, trader_name, model_id, status, prompt_chars,
                       response_chars, prompt_text, response_text, truncated
                FROM trading.ai_io_debug_log
                WHERE category = %s
                  AND created_at >= now() - (%s || ' hours')::interval
                ORDER BY created_at DESC
                """,
                (category, hours),
            )
            return cur.fetchall()


def build_report(rows):
    statuses = Counter(row[4] for row in rows)
    models = Counter((row[3], row[4]) for row in rows)
    prompt_chars = [int(row[5] or 0) for row in rows]
    response_chars = [int(row[6] or 0) for row in rows]
    section_values = {}
    kb_lengths = []
    generic_kb = 0
    skipped_with_prompt = 0
    market_symbol_counts = []
    market_age_values = []
    market_parse_errors = Counter()

    for row in rows:
        _, _, trader, _, status, prompt_len, _, prompt, _, _ = row
        prompt = prompt or ""
        if status == "model_skipped" and int(prompt_len or 0) > 0:
            skipped_with_prompt += 1
        for key, value in section_lengths(prompt).items():
            section_values.setdefault(key, []).append(value)
        kb = section(prompt, "KB:")
        if kb:
            kb_lengths.append((len(kb), trader, status))
            if is_generic_kb(kb):
                generic_kb += 1
        features, error = parse_market_features(prompt)
        if error:
            market_parse_errors[error] += 1
            continue
        if isinstance(features, dict):
            market_symbol_counts.append(len(features))
            for item in features.values():
                if isinstance(item, dict) and "age_s" in item:
                    try:
                        market_age_values.append(float(item["age_s"]))
                    except Exception:
                        pass

    section_summary = {
        key: {
            "avg": round(mean(values), 1),
            "max": max(values),
        }
        for key, values in section_values.items()
        if values
    }
    section_summary = dict(sorted(section_summary.items(), key=lambda item: item[1]["avg"], reverse=True))

    return {
        "rows": len(rows),
        "statuses": dict(statuses),
        "models": {f"{model or 'none'}:{status}": count for (model, status), count in models.most_common()},
        "prompt_chars": {
            "avg": round(mean(prompt_chars), 1) if prompt_chars else 0,
            "p50": percentile(prompt_chars, 0.50),
            "p90": percentile(prompt_chars, 0.90),
            "max": max(prompt_chars) if prompt_chars else 0,
        },
        "response_chars": {
            "avg": round(mean(response_chars), 1) if response_chars else 0,
            "max": max(response_chars) if response_chars else 0,
        },
        "sections": section_summary,
        "kb": {
            "rows_with_kb": len(kb_lengths),
            "generic_rows": generic_kb,
            "top_lengths": sorted(kb_lengths, reverse=True)[:10],
        },
        "market_features": {
            "symbol_count_avg": round(mean(market_symbol_counts), 1) if market_symbol_counts else 0,
            "symbol_count_min": min(market_symbol_counts) if market_symbol_counts else 0,
            "symbol_count_max": max(market_symbol_counts) if market_symbol_counts else 0,
            "age_s_avg": round(mean(market_age_values), 1) if market_age_values else None,
            "age_s_max": max(market_age_values) if market_age_values else None,
            "parse_errors": dict(market_parse_errors),
        },
        "warnings": {
            "model_skipped_rows_with_prompt": skipped_with_prompt,
        },
    }


def print_report(report):
    print(f"AI prompt log analysis: rows={report['rows']}")
    print(f"statuses={report['statuses']}")
    print(f"prompt_chars={report['prompt_chars']}")
    print(f"response_chars={report['response_chars']}")
    print("sections avg/max:")
    for key, data in report["sections"].items():
        print(f"- {key}: avg={data['avg']} max={data['max']}")
    print(f"kb={report['kb']}")
    print(f"market_features={report['market_features']}")
    print(f"warnings={report['warnings']}")


def main():
    parser = argparse.ArgumentParser(description="Analyze stored AI prompt/response debug logs.")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--category", default="trader")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(fetch_rows(args.hours, args.category))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
