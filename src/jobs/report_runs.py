from __future__ import annotations

import argparse
import json
import sys

from src.observability.event_store import JsonlEventStore
from src.observability.metrics import summarize_events


def report_runs_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize local pipeline observation events.")
    parser.add_argument("--event-store-path", default=".runs/events.jsonl", help="Path to JSONL observation event store.")
    parser.add_argument("--market", help="Filter by market id.")
    parser.add_argument("--language", help="Filter by language.")
    parser.add_argument("--event-type", help="Filter by event type.")
    parser.add_argument("--success", choices=["true", "false"], help="Filter by success value.")
    parser.add_argument("--limit", type=int, help="Limit events before summarizing.")
    namespace = parser.parse_args(args)

    if namespace.limit is not None and namespace.limit <= 0:
        print(json.dumps({"success": False, "status": "REPORT_ARGUMENT_ERROR", "errors": [{"message": "limit must be greater than 0."}]}, indent=2))
        return 2

    try:
        success_filter = None
        if namespace.success is not None:
            success_filter = namespace.success == "true"
        events = JsonlEventStore(namespace.event_store_path).filter_events(
            event_type=namespace.event_type,
            market_id=namespace.market,
            language=namespace.language,
            success=success_filter,
            limit=namespace.limit,
        )
        payload = {
            "success": True,
            "status": "REPORT_GENERATED",
            "filters": {
                "event_store_path": namespace.event_store_path,
                "market": namespace.market,
                "language": namespace.language,
                "event_type": namespace.event_type,
                "success": success_filter,
                "limit": namespace.limit,
            },
            "summary": summarize_events(events),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "status": "REPORT_FAILED", "errors": [{"type": "exception", "message": str(exc)}]}, indent=2))
        return 1


def main() -> int:
    return report_runs_command()


if __name__ == "__main__":
    sys.exit(main())
