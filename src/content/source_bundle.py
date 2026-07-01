from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from src.ingest.normalize import NormalizedNewsItem
from src.ingest.tradingview import SourceFetchResult


class SourceBundle(BaseModel):
    bundle_id: str
    market_id: str
    symbol: str
    language: str
    sources: list[NormalizedNewsItem] = Field(default_factory=list)
    source_bundle_hash: str | None = None
    missing_source_ids: list[str] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    source_trace: dict = Field(default_factory=dict)


class SourceBundleBuilder:
    def build(self, market, fetch_result: SourceFetchResult) -> SourceBundle:
        policy = market.content.source_policy
        warnings = list(fetch_result.warnings or [])
        errors = list(fetch_result.errors or [])
        sources = list(fetch_result.items or [])[: policy.max_sources]

        if not fetch_result.success:
            errors.append({"type": "source_fetch_failed", "market_id": market.id})
        if len(sources) < policy.min_sources:
            errors.append(
                {
                    "type": "not_enough_sources",
                    "min_sources": policy.min_sources,
                    "source_count": len(sources),
                }
            )
        if policy.require_body and sources and not any((source.content or source.summary) for source in sources):
            errors.append({"type": "missing_source_content"})

        bundle_id = _bundle_id(market.id, market.symbol, market.content.language, sources)
        return SourceBundle(
            bundle_id=bundle_id,
            source_bundle_hash=bundle_id,
            market_id=market.id,
            symbol=market.symbol,
            language=market.content.language,
            sources=sources,
            warnings=warnings,
            errors=errors,
            source_trace={
                "source_ids": [source.source_id for source in sources],
                "source_count": len(sources),
                "fetch_success": fetch_result.success,
                "fetch_item_count": len(fetch_result.items or []),
            },
        )


def source_bundle_to_dict(bundle: SourceBundle) -> dict[str, Any]:
    if hasattr(bundle, "model_dump"):
        return bundle.model_dump()
    return bundle.dict()


def _bundle_id(market_id: str, symbol: str, language: str, sources: list[NormalizedNewsItem]) -> str:
    source_ids = sorted(source.source_id for source in sources)
    basis = "|".join([market_id, symbol, language, *source_ids])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
