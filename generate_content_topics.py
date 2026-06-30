"""Generate minimal USDIDR content topic candidates from stored forex news."""

import argparse
import json
from typing import List, Optional

from dotenv import load_dotenv

from content_topics import (
    SUPPORTED_TOPIC_SYMBOL,
    build_topic_generation_result,
    fetch_usdidr_news_for_topics,
    json_safe,
)
from fetch_forex_news_json import get_postgres_dsn, utc_now_iso


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate USDIDR topic candidates from stored forex news.")
    parser.add_argument("--symbol", default=SUPPORTED_TOPIC_SYMBOL, help="Only USDIDR is supported in the first version.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum stored forex_news rows to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Do not insert generated topics into Postgres.")
    return parser


def unsupported_symbol_result(symbol: str) -> dict:
    symbol = str(symbol or "").upper()
    return {
        "generated_at": utc_now_iso(),
        "symbol": symbol,
        "summary": {
            "news_checked": 0,
            "topics_generated": 0,
            "topics_inserted": 0,
            "topics_skipped": 0,
            "topics_failed": 0,
        },
        "topics": [],
        "errors": [
            {
                "symbol": symbol,
                "error": f"Unsupported symbol for topic generation: {symbol}. Only USDIDR is supported.",
            }
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    symbol = str(args.symbol or "").upper()

    try:
        if symbol != SUPPORTED_TOPIC_SYMBOL:
            result = unsupported_symbol_result(symbol)
        else:
            dsn = get_postgres_dsn()
            news_rows = fetch_usdidr_news_for_topics(dsn, limit=max(args.limit, 0))
            result = build_topic_generation_result(
                symbol=symbol,
                news_rows=news_rows,
                dsn=dsn,
                dry_run=args.dry_run,
            )
    except Exception as exc:
        result = {
            "generated_at": utc_now_iso(),
            "symbol": symbol,
            "summary": {
                "news_checked": 0,
                "topics_generated": 0,
                "topics_inserted": 0,
                "topics_skipped": 0,
                "topics_failed": 0,
            },
            "topics": [],
            "errors": [{"symbol": symbol, "error": str(exc)}],
        }

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
