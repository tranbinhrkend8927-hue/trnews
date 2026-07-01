from dataclasses import dataclass

from src.jobs.idempotency import (
    compute_content_job_key,
    compute_daily_content_job_key,
    compute_pipeline_run_id,
    compute_source_bundle_hash,
    compute_source_item_fingerprint,
    sha256_hex,
    stable_json_dumps,
)


@dataclass
class SourceModel:
    source_id: str
    news_id: str
    url: str
    canonical_url: str
    title: str
    published_at: str
    provider: str


def test_stable_json_dumps_key_order():
    assert stable_json_dumps({"b": 2, "a": 1}) == stable_json_dumps({"a": 1, "b": 2})


def test_sha256_hex_stable():
    assert sha256_hex("abc") == sha256_hex("abc")


def test_source_fingerprint_supports_dict_and_model():
    source = {
        "source_id": "src-1",
        "news_id": "101",
        "url": "https://example.com/a",
        "canonical_url": "https://example.com/a",
        "title": "Title",
        "published_at": "2026",
        "provider": "TradingView",
    }
    model = SourceModel(**source)

    assert compute_source_item_fingerprint(source) == compute_source_item_fingerprint(model)


def test_source_bundle_hash_order_insensitive():
    one = {"market_id": "m", "symbol": "S", "language": "id", "sources": [{"source_id": "1"}, {"source_id": "2"}]}
    two = {"market_id": "m", "symbol": "S", "language": "id", "sources": [{"source_id": "2"}, {"source_id": "1"}]}

    assert compute_source_bundle_hash(one) == compute_source_bundle_hash(two)


def test_source_bundle_hash_includes_market_symbol_language():
    base = {"market_id": "m", "symbol": "S", "language": "id", "sources": [{"source_id": "1"}]}
    changed = {"market_id": "m2", "symbol": "S", "language": "id", "sources": [{"source_id": "1"}]}

    assert compute_source_bundle_hash(base) != compute_source_bundle_hash(changed)


def test_content_job_key_format():
    key = compute_content_job_key(market_id="m", symbol="S", language="id", task="article_draft", source_bundle_hash="abcdef1234567890")

    assert key == "m:S:id:article_draft:abcdef1234567890"


def test_daily_content_job_key_format():
    key = compute_daily_content_job_key(market_id="m", symbol="S", language="id", task="article_draft", date="2026-07-01")

    assert key == "m:S:id:article_draft:2026-07-01"


def test_pipeline_run_id_contains_fields():
    run_id = compute_pipeline_run_id(market_id="m", symbol="S", language="id", timestamp="20260701T120000Z")

    assert run_id == "run-m-S-id-20260701T120000Z"
