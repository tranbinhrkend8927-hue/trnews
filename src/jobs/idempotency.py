from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any


def stable_json_dumps(value: object) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def compute_source_item_fingerprint(source: object) -> str:
    data = _as_mapping(source)
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    fingerprint = {
        "source_id": data.get("source_id"),
        "news_id": data.get("news_id") or raw.get("news_id") or raw.get("id"),
        "url": data.get("url"),
        "canonical_url": data.get("canonical_url"),
        "title": data.get("title"),
        "published_at": data.get("published_at"),
        "provider": data.get("provider"),
    }
    return sha256_hex(stable_json_dumps(fingerprint))


def compute_source_bundle_hash(source_bundle: object) -> str:
    data = _as_mapping(source_bundle)
    sources = data.get("sources") or []
    source_fingerprints = sorted(compute_source_item_fingerprint(source) for source in sources)
    payload = {
        "market_id": data.get("market_id"),
        "symbol": data.get("symbol"),
        "language": data.get("language"),
        "sources": source_fingerprints,
    }
    return sha256_hex(stable_json_dumps(payload))


def compute_content_job_key(
    *,
    market_id: str,
    symbol: str,
    language: str,
    task: str,
    source_bundle_hash: str,
) -> str:
    return f"{market_id}:{symbol}:{language}:{task}:{source_bundle_hash[:16]}"


def compute_daily_content_job_key(
    *,
    market_id: str,
    symbol: str,
    language: str,
    task: str,
    date: str | None = None,
) -> str:
    day = date or datetime.now(timezone.utc).date().isoformat()
    return f"{market_id}:{symbol}:{language}:{task}:{day}"


def compute_pipeline_run_id(
    *,
    market_id: str,
    symbol: str,
    language: str,
    timestamp: str | None = None,
) -> str:
    stamp = timestamp or datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    safe_market = str(market_id).replace(":", "_")
    safe_symbol = str(symbol).replace(":", "_")
    safe_language = str(language).replace(":", "_")
    return f"run-{safe_market}-{safe_symbol}-{safe_language}-{stamp}"


def _as_mapping(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if is_dataclass(value):
        return asdict(value)
    return dict(value)  # type: ignore[arg-type]


def _jsonable(value: object):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    if is_dataclass(value):
        return _jsonable(asdict(value))
    return str(value)
