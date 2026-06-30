import json

import generate_llm_article_draft
import llm_article_drafts
from llm_gateway import LLMGateway, MockLLMProvider


def _topic(**overrides):
    topic = {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "macro_event_watch",
        "title": "USD/IDR Bergerak Menjelang Data AS",
        "status": "candidate",
        "reason_json": {"source_news_ids": [10]},
        "source_news_ids": [10],
    }
    topic.update(overrides)
    return topic


def _source_bundle(**overrides):
    bundle = {
        "topic_id": 1,
        "topic_type": "macro_event_watch",
        "symbol": "USDIDR",
        "source_news_ids": [10],
        "sources": [
            {
                "news_id": 10,
                "symbol": "USDIDR",
                "title": "USD/IDR dan CPI menjadi perhatian",
                "summary": "Pasar mencermati data AS.",
                "content": None,
                "url": "https://example.com/source-10",
                "canonical_url": None,
                "source": "Example",
                "source_url": None,
                "published_at": None,
                "fetched_at": None,
                "locale": "id",
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
        "reason_json": {"source_news_ids": [10]},
        "source_trace": {"topic_status": "candidate"},
    }
    bundle.update(overrides)
    return bundle


def _body(extra=""):
    return "\n\n".join(
        [
            "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia berdasarkan sumber berita yang tersimpan.",
            "Apa yang terjadi?\nSumber terkait menyoroti Rupiah, Dolar AS, Bank Indonesia, dan The Fed dalam konteks pasar.",
            "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami mengapa berita makro dapat menjadi perhatian bagi Rupiah.",
            "Faktor yang perlu dipantau\nPembaca dapat mencermati komunikasi bank sentral dan agenda makro dari sumber resmi.",
            "Apa dampaknya bagi pembaca Indonesia?\nArtikel ini memberi konteks umum tanpa menyimpulkan arah pasar sebagai sesuatu yang pasti.",
            "FAQ\nQ: Apakah ini rekomendasi transaksi?\nA: Tidak, ini informasi umum.",
            "Sumber\nSource news ID 10: USD/IDR dan CPI menjadi perhatian\nURL: https://example.com/source-10",
            "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
            extra,
        ]
    )


def _llm_output(**overrides):
    output = {
        "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau Pembaca Indonesia",
        "slug": "usd-idr-rupiah-faktor-yang-perlu-dipantau",
        "summary": "Ringkasan edukatif tentang USD/IDR dan Rupiah berdasarkan sumber berita yang tersimpan.",
        "body": _body(),
        "seo_title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia berdasarkan sumber berita tersimpan.",
        "faq": [{"question": "Apakah ini rekomendasi transaksi?", "answer": "Tidak."}],
        "sources_used": [{"news_id": 10, "title": "USD/IDR dan CPI menjadi perhatian"}],
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        "uncertain_claims": [],
        "language": "id",
    }
    output.update(overrides)
    return output


def _gateway(output=None, *, mode=None):
    if mode:
        return LLMGateway(provider=MockLLMProvider(mode=mode))
    return LLMGateway(
        provider=MockLLMProvider(
            responses=[
                {
                    "success": True,
                    "provider": "mock",
                    "model": "mock-model",
                    "content": output or _llm_output(),
                    "raw_response": {"mock": True},
                    "usage": {},
                }
            ]
        )
    )


def test_mock_llm_success_generates_draft_candidate():
    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        _gateway(),
    )

    assert result["success"] is True
    candidate = result["draft_candidate"]
    assert candidate["status"] == "pending_review"
    assert candidate["status"] != "approved"
    assert candidate["status"] != "published"
    assert candidate["published_at"] is None
    assert candidate["risk_disclaimer_included"] is True
    assert candidate["sources_json"]["sources"][0]["title"] == "USD/IDR dan CPI menjadi perhatian"
    assert isinstance(candidate["sources_used"], list)
    assert isinstance(candidate["uncertain_claims"], list)
    assert result["safety_result"]
    assert result["quality_result"]


def test_result_is_json_serializable():
    result = llm_article_drafts.generate_llm_article_draft_candidate(_topic(), _source_bundle(), _gateway())

    dumped = json.dumps(result, ensure_ascii=False)

    assert "draft_candidate" in dumped


def test_empty_source_bundle_does_not_call_llm():
    provider = MockLLMProvider(responses=[{"success": True, "content": _llm_output()}])

    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(sources=[]),
        LLMGateway(provider=provider),
    )

    assert result["success"] is False
    assert result["errors"][0]["type"] == "missing_sources"
    assert provider.call_count == 0
    assert result["llm_result"] == {}


def test_unsupported_language_does_not_call_llm():
    provider = MockLLMProvider(responses=[{"success": True, "content": _llm_output()}])

    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        LLMGateway(provider=provider),
        language="ja",
    )

    assert result["success"] is False
    assert result["errors"][0]["type"] == "unsupported_language"
    assert provider.call_count == 0


def test_gateway_failure_returns_structured_error_without_safety_or_quality():
    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        _gateway(mode="api_error"),
    )

    assert result["success"] is False
    assert result["errors"][0]["type"] == "api_error"
    assert result["safety_result"] == {}
    assert result["quality_result"] == {}


def test_invalid_json_returns_structured_error():
    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        _gateway(mode="invalid_json"),
    )

    assert result["success"] is False
    assert result["errors"][0]["type"] == "invalid_json"


def test_schema_failure_returns_structured_error():
    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        _gateway({"title": "Only title"}),
    )

    assert result["success"] is False
    assert result["errors"][0]["type"] == "schema_validation_error"
    assert result["draft_candidate"] == {}


def test_safety_failed_is_reflected_and_quality_not_ready():
    unsafe_output = _llm_output(body=_body("Strategi ini dijamin profit."))

    result = llm_article_drafts.generate_llm_article_draft_candidate(
        _topic(),
        _source_bundle(),
        _gateway(unsafe_output),
    )

    assert result["success"] is True
    assert result["safety_result"]["fact_check_status"] == "failed"
    assert result["draft_candidate"]["fact_check_status"] == "failed"
    assert result["quality_result"]["level"] == "blocked"
    assert result["quality_result"]["level"] != "ready_for_review"


def test_cli_requires_dry_run(capsys):
    exit_code = generate_llm_article_draft.main(["--topic-id", "1"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"][0]["type"] == "dry_run_required"


def test_cli_mock_provider_dry_run_does_not_write_db(monkeypatch, capsys):
    calls = {"fetch_topic": 0, "fetch_sources": 0}
    monkeypatch.setattr(generate_llm_article_draft, "get_postgres_dsn", lambda: "postgresql://example/db")

    def fake_fetch_topic(dsn, topic_id):
        calls["fetch_topic"] += 1
        return _topic(id=topic_id)

    def fake_fetch_sources(dsn, topic):
        calls["fetch_sources"] += 1
        return {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []}

    monkeypatch.setattr(generate_llm_article_draft, "fetch_topic_for_draft", fake_fetch_topic)
    monkeypatch.setattr(generate_llm_article_draft, "fetch_source_news_for_topic", fake_fetch_sources)

    exit_code = generate_llm_article_draft.main(["--topic-id", "7", "--provider", "mock", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["topic_id"] == 7
    assert payload["provider"] == "mock"
    assert payload["dry_run"] is True
    assert payload["summary"]["would_write_db"] is False
    assert payload["summary"]["would_publish"] is False
    assert payload["draft_candidate"]["status"] == "pending_review"
    assert payload["draft_candidate"]["published_at"] is None
    assert calls == {"fetch_topic": 1, "fetch_sources": 1}


def test_cli_openrouter_provider_is_explicit_and_still_dry_run(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(generate_llm_article_draft, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_llm_article_draft, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        generate_llm_article_draft,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )

    class FakeGateway:
        provider = type("Provider", (), {"provider_name": "openrouter"})()

        def generate_json(self, task_name, messages, schema, config=None):
            captured["config"] = config
            return {
                "success": True,
                "provider": "openrouter",
                "model": "unit-model",
                "task_name": task_name,
                "output": _llm_output(),
                "raw_response": {},
                "usage": {},
                "latency_ms": 0,
                "error": None,
            }

    monkeypatch.setattr(generate_llm_article_draft, "build_gateway", lambda provider_name, source_bundle: FakeGateway())

    exit_code = generate_llm_article_draft.main(["--topic-id", "7", "--provider", "openrouter", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider"] == "openrouter"
    assert captured["config"]["provider"] == "openrouter"
    assert payload["summary"]["would_write_db"] is False
    assert payload["summary"]["would_publish"] is False
