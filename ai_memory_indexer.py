#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from hybrid_rag import index_hybrid_memory


def parse_args():
    parser = argparse.ArgumentParser(description="Индексирует торговую память и новости в Qdrant.")
    parser.add_argument("--mode", choices=["all", "setups", "news"], default="all")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--news-lookback-hours", type=int, default=168)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--force", action="store_true", help="Переиндексировать даже неизменившиеся документы.")
    parser.add_argument("--dry-run", action="store_true", help="Проверить выборку без записи в Qdrant.")
    parser.add_argument("--json", action="store_true", help="Вывести только JSON-статистику.")
    return parser.parse_args()


def main():
    args = parse_args()
    stats = index_hybrid_memory(
        mode=args.mode,
        lookback_days=args.lookback_days,
        news_lookback_hours=args.news_lookback_hours,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
