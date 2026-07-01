from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .dedupe import dedupe_news_items
from .normalize import NormalizedNewsItem, normalize_tradingview_item


class SourceFetchResult(BaseModel):
    success: bool
    market_id: str
    symbol: str
    language: str
    items: list[NormalizedNewsItem] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)


class TradingViewNewsAdapter:
    def __init__(self, scraper=None):
        self.scraper = scraper

    def fetch(self, market) -> SourceFetchResult:
        try:
            raw_items = self._fetch_raw_items(market)
        except Exception as exc:
            return SourceFetchResult(
                success=False,
                market_id=market.id,
                symbol=market.symbol,
                language=market.tradingview.language,
                errors=[{"type": "tradingview_fetch_failed", "error": str(exc)}],
            )

        normalized: list[NormalizedNewsItem] = []
        warnings: list[dict] = []
        for index, raw_item in enumerate(raw_items or []):
            try:
                normalized.append(normalize_tradingview_item(raw_item, market=market))
            except Exception as exc:
                warnings.append(
                    {
                        "type": "normalize_failed",
                        "index": index,
                        "error": str(exc),
                        "raw": raw_item,
                    }
                )

        return SourceFetchResult(
            success=True,
            market_id=market.id,
            symbol=market.symbol,
            language=market.tradingview.language,
            items=dedupe_news_items(normalized),
            warnings=warnings,
        )

    def _fetch_raw_items(self, market) -> list[dict[str, Any]]:
        scraper = self.scraper or self._default_scraper()
        tv = market.tradingview
        kwargs = {
            "symbol": market.symbol,
            "exchange": market.exchange,
            "provider": tv.provider,
            "area": tv.area,
            "sort": tv.sort,
            "section": tv.section,
            "language": tv.language,
            "max_headlines": tv.max_headlines,
            "max_articles": tv.max_articles,
        }
        for method_name in ("fetch_news", "scrape_news", "get_news"):
            method = getattr(scraper, method_name, None)
            if method:
                return _coerce_items(method(**kwargs))
        if hasattr(scraper, "scrape_headlines"):
            headlines = scraper.scrape_headlines(
                symbol=market.symbol,
                exchange=market.exchange,
                provider=tv.provider,
                area=tv.area,
                sort=tv.sort,
                section=tv.section,
                language=tv.language,
            )
            items = _coerce_items(headlines)[: tv.max_headlines]
            return _enrich_headline_items(scraper, items, max_articles=tv.max_articles)
        if callable(scraper):
            return _coerce_items(scraper(market))
        raise RuntimeError("TradingView scraper does not expose a supported news fetch method.")

    def _default_scraper(self):
        from tradingview_scraper.symbols.news import NewsScraper

        self.scraper = NewsScraper(export_result=False)
        return self.scraper


def _coerce_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("items"), list):
            return [dict(item) for item in value["items"]]
        if isinstance(value.get("results"), list):
            return [dict(item) for item in value["results"]]
        return [dict(value)]
    return [dict(item) for item in (value or [])]


def _enrich_headline_items(scraper, items: list[dict[str, Any]], *, max_articles: int) -> list[dict[str, Any]]:
    scrape_many = getattr(scraper, "scrape_news_contents", None)
    if not scrape_many or max_articles <= 0:
        return items

    enrichable: list[tuple[int, str]] = []
    for index, item in enumerate(items[:max_articles]):
        story_path = _story_path(item)
        if story_path:
            enrichable.append((index, story_path))
    if not enrichable:
        return items

    details = scrape_many([story_path for _, story_path in enrichable])
    detail_items = details.get("results") if isinstance(details, dict) else details
    for (index, _), detail in zip(enrichable, detail_items or []):
        if isinstance(detail, dict):
            items[index] = _merge_article_detail(items[index], detail)
    return items


def _story_path(item: dict[str, Any]) -> str | None:
    value = item.get("storyPath") or item.get("story_path") or item.get("path")
    if not value:
        return None
    text = str(value).strip()
    return text if text.startswith("/") else None


def _merge_article_detail(item: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(item)
    if detail.get("title"):
        merged["title"] = detail["title"]
    if detail.get("published_datetime"):
        merged["published_datetime"] = detail["published_datetime"]
    if detail.get("body"):
        merged["body"] = detail["body"]
    if detail.get("tags"):
        merged["tags"] = detail["tags"]
    if detail.get("breadcrumbs"):
        merged["breadcrumbs"] = detail["breadcrumbs"]
    return merged
