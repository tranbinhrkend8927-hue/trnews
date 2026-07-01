from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class NormalizedNewsItem(BaseModel):
    source_id: str
    provider: Optional[str] = None
    symbol: str
    exchange: str
    language: str
    locale: Optional[str] = None
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    fetched_at: str
    raw: dict = Field(default_factory=dict)


def normalize_tradingview_item(raw_item: dict[str, Any], *, market) -> NormalizedNewsItem:
    raw = dict(raw_item or {})
    title = _first_text(raw, ["title", "headline", "name"])
    if not title:
        raise ValueError("TradingView news item title is required.")

    story_path = _first_text(raw, ["story_path", "storyPath", "path"])
    url = _first_text(raw, ["url", "link", "source_url"])
    if not url and story_path:
        url = f"https://www.tradingview.com{story_path}" if story_path.startswith("/") else story_path

    content = _content_text(raw)
    source_id = _source_id(raw, title=title, url=url)
    return NormalizedNewsItem(
        source_id=source_id,
        provider=_first_text(raw, ["provider", "source", "source_name"]),
        symbol=market.symbol,
        exchange=market.exchange,
        language=market.tradingview.language,
        locale=market.tradingview.locale,
        title=title,
        summary=_first_text(raw, ["summary", "description", "shortDescription"]),
        content=content,
        url=url,
        canonical_url=_first_text(raw, ["canonical_url", "canonicalUrl"]) or url,
        published_at=_first_text(raw, ["published_at", "published", "published_datetime", "datetime"]),
        fetched_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        raw=raw,
    )


def _source_id(raw: dict[str, Any], *, title: str, url: str | None) -> str:
    for key in ("source_id", "id", "news_id", "story_path", "storyPath", "url"):
        value = raw.get(key)
        if value not in (None, ""):
            return _stable_id(str(value))
    published_at = raw.get("published_at") or raw.get("published") or ""
    basis = "|".join(part for part in [title, url or "", str(published_at)] if part)
    return _stable_id(basis)


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _first_text(raw: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value).strip()
        if text:
            return text
    return None


def _content_text(raw: dict[str, Any]) -> str | None:
    content = raw.get("content") or raw.get("body")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("content") or item.get("text")
            else:
                value = item
            if value:
                parts.append(str(value).strip())
        return "\n".join(part for part in parts if part) or None
    return None
