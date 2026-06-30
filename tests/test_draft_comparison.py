import json

from news_pipeline import compare_article_drafts
from news_pipeline import draft_comparison
from news_pipeline.llm_gateway import LLMGateway, MockLLMProvider


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


def _candidate(**overrides):
    candidate = {
        "topic_id": 1,
        "symbol": "USDIDR",
        "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau Pembaca Indonesia",
        "slug": "usd-idr-rupiah-faktor-yang-perlu-dipantau",
        "summary": "Ringkasan edukatif tentang USD/IDR dan Rupiah berdasarkan sumber berita yang tersimpan.",
        "body": _body(),
        "seo_title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia berdasarkan sumber berita tersimpan.",
        "faq": [{"question": "Apakah ini rekomendasi transaksi?", "answer": "Tidak."}],
        "sources_used": [{"news_id": 10, "title": "USD/IDR dan CPI menjadi perhatian", "url": "https://example.com/source-10"}],
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        "uncertain_claims": [],
        "language": "id",
        "status": "pending_review",
        "fact_check_status": "pending",
        "published_at": None,
        "risk_disclaimer_included": True,
        "sources_json": _source_bundle(),
    }
    candidate.update(overrides)
    return candidate


def _safety(**overrides):
    result = {"passed": True, "violations": [], "fact_check_status": "pending"}
    result.update(overrides)
    return result


def _quality(score=85, level="ready_for_review", blocking_issues=None, warnings=None):
    return {
        "passed": not blocking_issues,
        "score": score,
        "level": level,
        "recommendation": "pending_review",
        "checks": [],
        "blocking_issues": blocking_issues or [],
        "warnings": warnings or [],
        "metadata": {"source_count": 1, "fact_check_status": "pending", "status": "pending_review"},
    }


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


def test_two_good_candidates_return_json_serializable_comparison():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(title="Rupiah dan USD/IDR: Konteks yang Perlu Dipantau"),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(84, "needs_review"),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(78, "needs_review"),
    )

    dumped = json.dumps(result, ensure_ascii=False)
    assert result["success"] is True
    assert result["recommendation"] == "needs_editor_review"
    assert result["winner"] is None
    assert "comparison" in dumped


def test_safety_failed_candidate_cannot_win():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(body=_body("Strategi ini dijamin profit.")),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(80, "needs_review"),
        llm_safety_result=_safety(passed=False, violations=[{"type": "profit_promise"}], fact_check_status="failed"),
        llm_quality_result=_quality(95, "ready_for_review"),
    )

    assert result["recommendation"] == "template"
    assert result["winner"] == "template"


def test_any_failed_safety_result_cannot_win():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(80, "needs_review"),
        llm_safety_result=_safety(
            passed=False,
            violations=[{"type": "missing_sources_for_financial_terms"}],
            fact_check_status="needs_sources",
        ),
        llm_quality_result=_quality(95, "ready_for_review"),
    )

    assert result["recommendation"] == "template"
    assert any(issue["type"] == "safety_failed" and issue["candidate"] == "llm" for issue in result["blocking_issues"])


def test_quality_blocked_candidate_cannot_win():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(80, "needs_review"),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(95, "blocked", blocking_issues=[{"name": "body_has_source_section"}]),
    )

    assert result["recommendation"] == "template"


def test_llm_source_grounding_error_cannot_directly_recommend_llm():
    llm = _candidate(sources_used=[{"news_id": 10, "url": "https://unknown.example/news"}])

    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        llm,
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(75, "needs_review"),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(95, "ready_for_review"),
    )

    assert result["recommendation"] == "template"
    assert result["recommendation"] != "llm"
    assert any(issue["type"] == "unknown_source_url" for issue in result["blocking_issues"])


def test_candidate_referencing_unknown_body_url_is_blocking():
    candidate = _candidate(body=_body("Sumber tambahan: https://unknown.example/news"))

    result = draft_comparison.validate_candidate_sources(candidate, _source_bundle())

    assert result["passed"] is False
    assert any(issue["type"] == "unknown_body_url" for issue in result["blocking_issues"])


def test_sources_used_mismatch_is_detected():
    candidate = _candidate(sources_used=[{"news_id": 999, "title": "Tidak ada di bundle"}])

    result = draft_comparison.validate_candidate_sources(candidate, _source_bundle())

    assert result["passed"] is False
    assert any(issue["type"] == "unknown_source_news_id" for issue in result["blocking_issues"])


def test_unsupported_financial_number_is_detected():
    candidate = _candidate(body=_body("USD/IDR bergerak ke 16000 menurut narasi artikel."))

    result = draft_comparison.detect_unsupported_financial_numbers(candidate, _source_bundle())

    assert result["passed"] is False
    assert any(issue["type"] == "unsupported_financial_number" for issue in result["blocking_issues"])


def test_close_scores_need_editor_review():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(title="Rupiah dan USD/IDR: Konteks yang Perlu Dipantau"),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(84, "needs_review"),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(79, "needs_review"),
    )

    assert result["recommendation"] == "needs_editor_review"


def test_only_template_good_recommends_template():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(body=""),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(80, "needs_review"),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(10, "blocked", blocking_issues=[{"name": "has_body"}]),
    )

    assert result["recommendation"] == "template"


def test_only_llm_good_recommends_llm():
    result = draft_comparison.compare_draft_candidates(
        _candidate(body=""),
        _candidate(),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(10, "blocked", blocking_issues=[{"name": "has_body"}]),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(80, "needs_review"),
    )

    assert result["recommendation"] == "llm"
    assert result["winner"] == "llm"


def test_both_blocking_recommends_neither():
    result = draft_comparison.compare_draft_candidates(
        _candidate(body=""),
        _candidate(body=""),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(10, "blocked", blocking_issues=[{"name": "has_body"}]),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(10, "blocked", blocking_issues=[{"name": "has_body"}]),
    )

    assert result["recommendation"] == "neither"
    assert result["winner"] is None


def test_recommendation_never_returns_approved_or_published():
    result = draft_comparison.compare_draft_candidates(
        _candidate(),
        _candidate(),
        source_bundle=_source_bundle(),
        template_safety_result=_safety(),
        template_quality_result=_quality(95),
        llm_safety_result=_safety(),
        llm_quality_result=_quality(70),
    )

    assert result["recommendation"] not in {"approved", "published"}
    assert result["winner"] not in {"approved", "published"}


def test_cli_requires_dry_run(capsys):
    exit_code = compare_article_drafts.main(["--topic-id", "1"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"][0]["type"] == "dry_run_required"


def test_cli_dry_run_outputs_comparison_with_default_mock(monkeypatch, capsys):
    monkeypatch.setattr(compare_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(compare_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        compare_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )

    exit_code = compare_article_drafts.main(["--topic-id", "7", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["provider"] == "mock"
    assert payload["dry_run"] is True
    assert payload["comparison_result"]
    assert payload["summary"]["would_write_db"] is False
    assert payload["summary"]["would_publish"] is False
    assert payload["template"]["draft"]["status"] == "pending_review"
    assert payload["llm"]["draft_candidate"]["status"] == "pending_review"


def test_cli_does_not_import_or_call_database_writes():
    assert not hasattr(compare_article_drafts, "save_article_draft_to_postgres")
    assert not hasattr(compare_article_drafts, "save_article_sources_to_postgres")
    assert not hasattr(compare_article_drafts, "save_article_review_to_postgres")


def test_cli_llm_failure_still_returns_template_result(monkeypatch, capsys):
    monkeypatch.setattr(compare_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(compare_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        compare_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(
        compare_article_drafts,
        "build_gateway",
        lambda provider_name, source_bundle: LLMGateway(provider=MockLLMProvider(mode="api_error")),
    )

    exit_code = compare_article_drafts.main(["--topic-id", "7", "--provider", "mock", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["template"]["draft"]
    assert payload["llm"]["errors"][0]["type"] == "api_error"
    assert payload["comparison_result"]["recommendation"] in {"template", "needs_editor_review"}


def test_cli_openrouter_requires_explicit_provider_and_is_still_dry_run(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(compare_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(compare_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        compare_article_drafts,
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
                "output": {
                    "title": _candidate()["title"],
                    "slug": _candidate()["slug"],
                    "summary": _candidate()["summary"],
                    "body": _candidate()["body"],
                    "seo_title": _candidate()["seo_title"],
                    "seo_description": _candidate()["seo_description"],
                    "faq": _candidate()["faq"],
                    "sources_used": _candidate()["sources_used"],
                    "risk_disclaimer": _candidate()["risk_disclaimer"],
                    "uncertain_claims": [],
                    "language": "id",
                },
                "raw_response": {},
                "usage": {},
                "latency_ms": 0,
                "error": None,
            }

    monkeypatch.setattr(compare_article_drafts, "build_gateway", lambda provider_name, source_bundle: FakeGateway())

    exit_code = compare_article_drafts.main(["--topic-id", "7", "--provider", "openrouter", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider"] == "openrouter"
    assert captured["config"]["provider"] == "openrouter"
    assert payload["summary"]["would_write_db"] is False
    assert payload["summary"]["would_publish"] is False
