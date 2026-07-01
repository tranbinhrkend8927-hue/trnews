from __future__ import annotations

import json
from pathlib import Path

from src.observability.events import ObservationEvent


class JsonlEventStore:
    def __init__(self, path: str = ".runs/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ObservationEvent) -> None:
        payload = event.model_dump() if hasattr(event, "model_dump") else event.dict()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def list_events(self) -> list[ObservationEvent]:
        if not self.path.exists():
            return []
        events: list[ObservationEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(ObservationEvent(**json.loads(line)))
            except Exception:
                continue
        return events

    def filter_events(
        self,
        *,
        event_type: str | None = None,
        market_id: str | None = None,
        language: str | None = None,
        success: bool | None = None,
        limit: int | None = None,
    ) -> list[ObservationEvent]:
        events = self.list_events()
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        if market_id is not None:
            events = [event for event in events if event.market_id == market_id]
        if language is not None:
            events = [event for event in events if event.language == language]
        if success is not None:
            events = [event for event in events if event.success is success]
        return events[:limit] if limit is not None else events
