import json

import smoke_article_pipeline


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


def _selected_payload(candidate_type="template"):
    return {
        "success": True,
        "topic_id": 1,
        "candidate_type": candidate_type,
        "provider": "mock",
        "selected_draft": {
            "topic_id": 1,
            "symbol": "USDIDR",
            "language": "id",
            "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
            "slug": "usd-idr-rupiah-faktor",
            "summary": "Ringkasan edukatif berdasarkan sumber tersimpan.",
            "body": "Body\n\nSumber\nURL: https://example.com/source-10\n\nCatatan risiko\nArtikel ini hanya untuk informasi dan edukasi.",
            "seo_title": "USD/IDR dan Rupiah",
            "seo_description": "Konteks USD/IDR untuk pembaca Indonesia.",
            "status": "pending_review",
            "fact_check_status": "pending",
            "risk_disclaimer_included": True,
            "sources_json": {"source_bundle": _source_bundle(), "candidate_type": candidate_type},
            "published_at": None,
        },
        "source_bundle": _source_bundle(),
        "safety_result": {"passed": True, "violations": [], "fact_check_status": "pending"},
        "quality_result": {"passed": True, "score": 90, "level": "ready_for_review", "blocking_issues": [], "warnings": []},
        "comparison_result": {
            "success": True,
            "mode": "selected_candidate_validation",
            "llm_status": "not_generated" if candidate_type == "template" else None,
            "recommendation": candidate_type,
        },
        "save_validation": {"can_save": True, "blockers": [], "warnings": []},
        "summary": {"would_write_db": True, "would_publish": False, "status_after_save": "pending_review"},
        "errors": [],
    }


def _article(**overrides):
    article = {
        "id": 7,
        "topic_id": 1,
        "symbol": "USDIDR",
        "language": "id",
        "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
        "slug": "usd-idr-rupiah-faktor",
        "summary": "Ringkasan edukatif berdasarkan sumber tersimpan.",
        "body": "\n\n".join(
            [
                "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia.",
                "Apa yang terjadi?\nBerdasarkan sumber berita yang tersimpan, pasar mencermati Rupiah dan Dolar AS.",
                "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami Rupiah, The Fed, dan Bank Indonesia.",
                "Faktor yang perlu dipantau\nPembaca dapat mencermati agenda makro dari sumber resmi.",
                "Apa dampaknya bagi pembaca Indonesia?\nArtikel ini memberi konteks umum tanpa menyimpulkan arah pasar.",
                "FAQ\nQ: Apakah ini rekomendasi transaksi?\nA: Tidak.",
                "Sumber\nSource news ID 10: USD/IDR dan CPI menjadi perhatian\nURL: https://example.com/source-10",
                "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
            ]
        ),
        "seo_title": "USD/IDR dan Rupiah",
        "seo_description": "Konteks USD/IDR untuk pembaca Indonesia.",
        "status": "pending_review",
        "fact_check_status": "pending",
        "risk_disclaimer_included": True,
        "sources_json": _source_bundle(),
        "published_at": None,
    }
    article.update(overrides)
    return article


def _article_sources():
    return [
        {
            "id": 1,
            "article_id": 7,
            "source_type": "forex_news",
            "source_name": "Example",
            "source_url": "https://example.com/source-10",
            "cited_claim": "USD/IDR dan CPI menjadi perhatian",
        }
    ]


def _patch_topic_flow(monkeypatch, *, candidate_payload=None, save_result=None):
    calls = {"gateway": 0, "payload": 0, "save": 0}
    monkeypatch.setattr(smoke_article_pipeline, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(smoke_article_pipeline, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        smoke_article_pipeline,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )

    def fake_gateway(provider, source_bundle):
        calls["gateway"] += 1
        if provider == "openrouter":
            raise AssertionError("default smoke tests must not call OpenRouter")
        return object()

    def fake_payload(topic, source_bundle, candidate_type, provider="mock", template_hint=None, language="id", gateway=None):
        calls["payload"] += 1
        assert candidate_type != "template" or gateway is None
        assert candidate_type != "llm" or gateway is not None
        return candidate_payload or _selected_payload(candidate_type)

    def fake_save(dsn, selected_payload, dry_run=True):
        calls["save"] += 1
        assert dry_run is False
        return save_result or {
            "success": True,
            "candidate_type": selected_payload["candidate_type"],
            "dry_run": False,
            "article_id": 77,
            "selected_draft": {**selected_payload["selected_draft"], "status": "pending_review", "published_at": None},
            "save_validation": selected_payload["save_validation"],
            "summary": {
                "inserted": 1,
                "skipped": 0,
                "article_sources_inserted": 1,
                "article_sources_failed": 0,
                "status": "pending_review",
                "would_publish": False,
            },
            "errors": [],
        }

    monkeypatch.setattr(smoke_article_pipeline, "build_gateway", fake_gateway)
    monkeypatch.setattr(smoke_article_pipeline, "build_selected_candidate_save_payload", fake_payload)
    monkeypatch.setattr(smoke_article_pipeline, "save_selected_candidate_to_postgres", fake_save)
    return calls


def _patch_review_flow(monkeypatch, article=None, sources=None):
    calls = {"review_save": 0, "status_update": 0}
    monkeypatch.setattr(smoke_article_pipeline, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(smoke_article_pipeline, "fetch_article_for_review", lambda dsn, article_id: article or _article(id=article_id))
    monkeypatch.setattr(smoke_article_pipeline, "fetch_article_sources_for_review", lambda dsn, article_id: sources or _article_sources())
    return calls


def test_topic_dry_run_outputs_steps(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "topic_pipeline_dry_run"
    assert [step["name"] for step in payload["steps"]] == [
        "fetch_topic",
        "build_source_bundle",
        "build_selected_candidate",
        "save_validation",
    ]
    assert payload["summary"]["would_write_db"] is False
    assert calls["save"] == 0


def test_candidate_template_does_not_call_llm(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    assert exit_code == 0
    assert calls["gateway"] == 0
    assert calls["payload"] == 1


def test_candidate_llm_uses_mock_gateway(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "llm", "--provider", "mock", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls["gateway"] == 1
    assert payload["candidate_type"] == "llm"


def test_default_provider_does_not_call_openrouter(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "llm", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider"] == "mock"
    assert calls["gateway"] == 1


def test_dry_run_does_not_write_db(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls["save"] == 0
    assert payload["summary"]["inserted"] == 0


def test_save_selected_draft_only_writes_articles_and_sources(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--save-selected-draft"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls["save"] == 1
    assert payload["summary"]["inserted"] == 1
    assert payload["summary"]["article_sources_inserted"] == 1
    assert payload["summary"]["status_after_save"] == "pending_review"


def test_save_selected_draft_does_not_write_article_reviews(monkeypatch, capsys):
    save_result = {
        "success": True,
        "candidate_type": "template",
        "dry_run": False,
        "article_id": 77,
        "selected_draft": _selected_payload()["selected_draft"],
        "save_validation": {"can_save": True, "blockers": [], "warnings": []},
        "summary": {"inserted": 1, "skipped": 0, "article_sources_inserted": 1, "article_sources_failed": 0, "status": "pending_review", "would_publish": False},
        "errors": [],
    }
    _patch_topic_flow(monkeypatch, save_result=save_result)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--save-selected-draft"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "article_reviews" not in dumped


def test_save_selected_draft_status_only_pending_review(monkeypatch, capsys):
    _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--save-selected-draft"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["result"]["save_result"]["selected_draft"]["status"] == "pending_review"
    assert payload["result"]["save_result"]["selected_draft"]["status"] not in {"approved", "published"}


def test_review_report_does_not_write_db(monkeypatch, capsys):
    _patch_review_flow(monkeypatch)
    monkeypatch.setattr(smoke_article_pipeline, "save_selected_candidate_to_postgres", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("review report must not save")))

    exit_code = smoke_article_pipeline.main(["--article-id", "7", "--review-report"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "review_report"
    assert "review_report" in payload["result"]


def test_review_decision_dry_run_does_not_write_review_or_update_status(monkeypatch, capsys):
    _patch_review_flow(monkeypatch)
    monkeypatch.setattr(smoke_article_pipeline, "save_selected_candidate_to_postgres", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("review decision must not save selected draft")))

    exit_code = smoke_article_pipeline.main(
        ["--article-id", "7", "--review-decision", "approved", "--reviewer", "editor", "--notes", "Smoke test review", "--dry-run"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "review_decision_dry_run"
    assert payload["result"]["validation"]["new_status"] == "approved"
    assert payload["steps"][-1]["summary"]["would_insert_review"] is False
    assert payload["steps"][-1]["summary"]["would_update_article"] is False


def test_invalid_arguments_return_structured_error(capsys):
    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run", "--save-selected-draft"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"][0]["type"] == "invalid_mode"


def test_review_decision_requires_dry_run(capsys):
    exit_code = smoke_article_pipeline.main(["--article-id", "7", "--review-decision", "approved"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["errors"][0]["type"] == "review_decision_dry_run_required"


def test_output_json_serializable(monkeypatch, capsys):
    _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    json.dumps(payload, ensure_ascii=False)


def test_no_notion_or_publish_paths_in_output(monkeypatch, capsys):
    _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    dumped = json.dumps(payload, ensure_ascii=False).lower()
    assert exit_code == 0
    assert "notion" not in dumped
    assert payload["summary"]["would_publish"] is False
    assert "published" not in payload["result"]["selected_payload"]["selected_draft"]["status"]


def test_default_tests_do_not_depend_on_real_db_or_network(monkeypatch, capsys):
    calls = _patch_topic_flow(monkeypatch)

    exit_code = smoke_article_pipeline.main(["--topic-id", "1", "--candidate", "template", "--dry-run"])

    assert exit_code == 0
    assert calls["payload"] == 1
