from __future__ import annotations

from src.ingest.normalize import NormalizedNewsItem


def dedupe_news_items(items: list[NormalizedNewsItem]) -> list[NormalizedNewsItem]:
    seen: set[str] = set()
    deduped: list[NormalizedNewsItem] = []
    for item in items or []:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _dedupe_key(item: NormalizedNewsItem) -> str:
    if item.canonical_url:
        return f"canonical_url:{item.canonical_url}"
    if item.url:
        return f"url:{item.url}"
    if item.source_id:
        return f"source_id:{item.source_id}"
    if item.title and item.published_at:
        return f"title_published:{item.title}|{item.published_at}"
    return f"title:{item.title}"
