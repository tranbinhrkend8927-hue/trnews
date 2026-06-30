import json
import sys
import types

import save_selected_article_draft
import selected_article_draft


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


def _llm_output():
    body = "\n\n".join(
        [
            "Pembuka singkat\nUSD/IDR dan Rupiah menjadi perhatian pembaca Indonesia berdasarkan sumber berita yang tersimpan.",
            "Apa yang terjadi?\nSumber terkait menyoroti konteks Rupiah, Dolar AS, Bank Indonesia, dan The Fed tanpa menyimpulkan arah pasar.",
            "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami berita makro secara hati-hati.",
            "Faktor yang perlu dipantau\nPembaca dapat mencermati komunikasi bank sentral dan agenda makro dari sumber resmi.",
            "Apa dampaknya bagi pembaca Indonesia?\nArtikel ini memberi konteks umum dan edukatif untuk memahami Rupiah.",
            "FAQ\nQ: Apakah ini rekomendasi transaksi?\nA: Tidak, ini informasi umum.",
            "Sumber\nSource news ID 10: USD/IDR dan CPI menjadi perhatian\nURL: https://example.com/source-10",
            "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        ]
    )
    return {
        "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau Pembaca Indonesia",
        "slug": "usd-idr-rupiah-faktor-yang-perlu-dipantau",
        "summary": "Ringkasan edukatif tentang USD/IDR dan Rupiah berdasarkan sumber berita yang tersimpan.",
        "body": body,
        "seo_title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia berdasarkan sumber berita tersimpan.",
        "faq": [{"question": "Apakah ini rekomendasi transaksi?", "answer": "Tidak."}],
        "sources_used": [{"news_id": 10, "title": "USD/IDR dan CPI menjadi perhatian", "url": "https://example.com/source-10"}],
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        "uncertain_claims": [],
        "language": "id",
    }


class FakeGateway:
    def __init__(self, output=None, success=True):
        self.calls = 0
        self.output = output or _llm_output()
        self.success = success
        self.provider = type("Provider", (), {"provider_name": "mock"})()

    def generate_json(self, task_name, messages, schema, config=None):
        self.calls += 1
        if not self.success:
            return {
                "success": False,
                "provider": "mock",
                "model": "mock-model",
                "task_name": task_name,
                "output": None,
                "raw_response": None,
                "usage": {},
                "latency_ms": 0,
                "error": {"type": "api_error", "message": "mock failure", "retryable": False},
            }
        return {
            "success": True,
            "provider": "mock",
            "model": "mock-model",
            "task_name": task_name,
            "output": self.output,
            "raw_response": {"secret": "raw response should not be persisted"},
            "usage": {},
            "latency_ms": 0,
            "error": None,
        }


def _install_fake_psycopg(monkeypatch, state):
    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if "article_reviews" in normalized:
                state["review_write_attempted"] = True
                raise AssertionError("P12 must not write article_reviews")
            if "SELECT 1 FROM generated_articles WHERE topic_id = %s" in normalized:
                self.next_fetchone = (1,) if state.get("duplicate") else None
                return
            if "INSERT INTO generated_articles" in normalized:
                state["article_inserts"].append(
                    {
                        "topic_id": params[0],
                        "status": params[9],
                        "fact_check_status": params[10],
                        "risk_disclaimer_included": params[11],
                        "sources_json": params[12],
                        "published_at": params[13],
                    }
                )
                self.next_fetchone = (77,)
                return
            if "INSERT INTO article_sources" in normalized:
                if state.get("fail_source_insert"):
                    raise RuntimeError("source insert failed")
                state["source_inserts"].append({"article_id": params[0], "source_url": params[3], "cited_claim": params[4]})
                self.next_fetchone = (len(state["source_inserts"]),)
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            state["commits"] += 1

        def rollback(self):
            state["rollbacks"] += 1

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda *args, **kwargs: FakeConnection()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)


def _saveable_payload(candidate_type="template", gateway=None):
    return selected_article_draft.build_selected_candidate_save_payload(
        _topic(),
        _source_bundle(),
        candidate_type,
        gateway=gateway,
    )


def test_cli_requires_explicit_candidate(capsys):
    exit_code = save_selected_article_draft.main(["--topic-id", "1", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["errors"][0]["type"] == "candidate_required"


def test_cli_invalid_candidate_returns_structured_error(capsys):
    exit_code = save_selected_article_draft.main(["--topic-id", "1", "--candidate", "auto", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["errors"][0]["type"] == "invalid_candidate"


def test_cli_requires_explicit_mode(capsys):
    exit_code = save_selected_article_draft.main(["--topic-id", "1", "--candidate", "template"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["errors"][0]["type"] == "mode_required"


def test_cli_rejects_dry_run_and_save_db_together(capsys):
    exit_code = save_selected_article_draft.main(["--topic-id", "1", "--candidate", "template", "--dry-run", "--save-db"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["errors"][0]["type"] == "invalid_mode"


def test_dry_run_does_not_write_generated_articles_or_sources(monkeypatch):
    payload = _saveable_payload()

    def fail_connect(*args, **kwargs):
        raise AssertionError("dry-run must not connect to postgres")

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = fail_connect
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)

    result = selected_article_draft.save_selected_candidate_to_postgres("postgresql://example/db", payload, dry_run=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["summary"]["inserted"] == 1
    assert result["summary"]["article_sources_inserted"] == 1


def test_candidate_template_does_not_call_llm():
    gateway = FakeGateway()

    payload = selected_article_draft.build_selected_candidate_save_payload(
        _topic(),
        _source_bundle(),
        "template",
        gateway=gateway,
    )

    assert payload["success"] is True
    assert gateway.calls == 0
    assert payload["comparison_result"]["llm_status"] == "not_generated"
    assert payload["save_validation"]["can_save"] is True


def test_candidate_llm_calls_mock_llm():
    gateway = FakeGateway()

    payload = selected_article_draft.build_selected_candidate_save_payload(
        _topic(),
        _source_bundle(),
        "llm",
        gateway=gateway,
    )

    assert payload["success"] is True
    assert gateway.calls == 1
    assert payload["candidate_type"] == "llm"


def test_template_build_selected_payload_forces_pending_review():
    payload = _saveable_payload("template")
    draft = payload["selected_draft"]

    assert payload["success"] is True
    assert draft["status"] == "pending_review"
    assert draft["published_at"] is None
    assert draft["status"] not in {"approved", "published"}
    assert draft["risk_disclaimer_included"] is True


def test_llm_build_selected_payload_forces_pending_review():
    payload = _saveable_payload("llm", gateway=FakeGateway())
    draft = payload["selected_draft"]

    assert payload["success"] is True
    assert draft["status"] == "pending_review"
    assert draft["published_at"] is None
    assert draft["status"] not in {"approved", "published"}


def test_safety_failed_blocks_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    safety = {"passed": False, "violations": [{"type": "profit_promise"}], "fact_check_status": "failed"}

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        safety,
        payload["quality_result"],
        payload["comparison_result"],
        "template",
    )

    assert validation["can_save"] is False
    assert any(item["type"] == "safety_failed" for item in validation["blockers"])


def test_quality_blocked_blocks_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    quality = dict(payload["quality_result"])
    quality["level"] = "blocked"
    quality["blocking_issues"] = [{"name": "has_body"}]

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        payload["safety_result"],
        quality,
        payload["comparison_result"],
        "template",
    )

    assert validation["can_save"] is False
    assert any(item["type"] == "quality_blocked" for item in validation["blockers"])


def test_needs_sources_blocks_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    draft["fact_check_status"] = "needs_sources"

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        {"passed": False, "violations": [{"type": "missing_sources_for_financial_terms"}], "fact_check_status": "needs_sources"},
        payload["quality_result"],
        payload["comparison_result"],
        "template",
    )

    assert validation["can_save"] is False
    assert any(item["type"] == "fact_check_needs_sources" for item in validation["blockers"])


def test_missing_source_bundle_blocks_save():
    payload = selected_article_draft.build_selected_candidate_save_payload(_topic(), _source_bundle(sources=[]), "template")

    assert payload["success"] is False
    assert any(item["type"] == "missing_source_bundle" for item in payload["save_validation"]["blockers"])


def test_comparison_neither_blocks_full_comparison_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    comparison = dict(payload["comparison_result"])
    comparison["is_full_comparison"] = True
    comparison["recommendation"] = "neither"

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        payload["safety_result"],
        payload["quality_result"],
        comparison,
        "template",
    )

    assert validation["can_save"] is False
    assert any(item["type"] == "comparison_neither" for item in validation["blockers"])


def test_recommendation_mismatch_warns_but_can_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    comparison = dict(payload["comparison_result"])
    comparison["is_full_comparison"] = True
    comparison["recommendation"] = "llm"

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        payload["safety_result"],
        payload["quality_result"],
        comparison,
        "template",
    )

    assert validation["can_save"] is True
    assert any(item["type"] == "comparison_recommendation_mismatch" for item in validation["warnings"])


def test_needs_editor_review_warns_but_can_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    comparison = dict(payload["comparison_result"])
    comparison["recommendation"] = "needs_editor_review"

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        payload["safety_result"],
        payload["quality_result"],
        comparison,
        "template",
    )

    assert validation["can_save"] is True
    assert any(item["type"] == "comparison_needs_editor_review" for item in validation["warnings"])


def test_template_llm_not_generated_warns_but_can_save():
    payload = _saveable_payload("template")

    assert payload["save_validation"]["can_save"] is True
    assert any(item["type"] == "llm_not_generated" for item in payload["save_validation"]["warnings"])


def test_unsupported_financial_number_blocks_save():
    payload = _saveable_payload("template")
    draft = dict(payload["selected_draft"])
    draft["sources_json"] = payload["source_bundle"]
    draft["body"] += "\nUSD/IDR bergerak ke 16000 menurut artikel."

    validation = selected_article_draft.validate_selected_candidate_for_save(
        draft,
        payload["source_bundle"],
        payload["safety_result"],
        payload["quality_result"],
        payload["comparison_result"],
        "template",
    )

    assert validation["can_save"] is False
    assert any(item["type"] == "unsupported_financial_number" for item in validation["blockers"])


def test_save_db_inserted_writes_generated_article_and_sources(monkeypatch):
    state = {"article_inserts": [], "source_inserts": [], "commits": 0, "rollbacks": 0, "review_write_attempted": False}
    _install_fake_psycopg(monkeypatch, state)
    payload = _saveable_payload("template")

    result = selected_article_draft.save_selected_candidate_to_postgres("postgresql://example/db", payload, dry_run=False)

    assert result["success"] is True
    assert result["article_id"] == 77
    assert state["article_inserts"][0]["status"] == "pending_review"
    assert state["article_inserts"][0]["published_at"] is None
    assert state["article_inserts"][0]["risk_disclaimer_included"] is True
    assert state["source_inserts"] == [{"article_id": 77, "source_url": "https://example.com/source-10", "cited_claim": "USD/IDR dan CPI menjadi perhatian"}]
    assert state["review_write_attempted"] is False


def test_duplicate_draft_skips_article_sources(monkeypatch):
    state = {"duplicate": True, "article_inserts": [], "source_inserts": [], "commits": 0, "rollbacks": 0, "review_write_attempted": False}
    _install_fake_psycopg(monkeypatch, state)
    payload = _saveable_payload("template")

    result = selected_article_draft.save_selected_candidate_to_postgres("postgresql://example/db", payload, dry_run=False)

    assert result["success"] is True
    assert result["summary"]["skipped"] == 1
    assert state["article_inserts"] == []
    assert state["source_inserts"] == []


def test_source_insert_failure_rolls_back(monkeypatch):
    state = {
        "fail_source_insert": True,
        "article_inserts": [],
        "source_inserts": [],
        "commits": 0,
        "rollbacks": 0,
        "review_write_attempted": False,
    }
    _install_fake_psycopg(monkeypatch, state)
    payload = _saveable_payload("template")

    result = selected_article_draft.save_selected_candidate_to_postgres("postgresql://example/db", payload, dry_run=False)

    assert result["success"] is False
    assert result["errors"][0]["type"] == "save_failed"
    assert state["rollbacks"] == 1


def test_sources_json_contains_required_summary_and_no_secret_fields():
    payload = _saveable_payload("llm", gateway=FakeGateway())
    sources_json = payload["selected_draft"]["sources_json"]
    dumped = json.dumps(sources_json, ensure_ascii=False)

    assert sources_json["candidate_type"] == "llm"
    assert "source_bundle" in sources_json
    assert "comparison_summary" in sources_json
    assert "safety_summary" in sources_json
    assert "quality_summary" in sources_json
    assert sources_json["llm_metadata"]["provider"] == "mock"
    assert "OPENROUTER_API_KEY" not in dumped
    assert "Authorization" not in dumped
    assert "raw_response" not in dumped
    assert "raw response should not be persisted" not in dumped


def test_output_json_serializable():
    payload = _saveable_payload("template")
    result = selected_article_draft.save_selected_candidate_to_postgres("postgresql://example/db", payload, dry_run=True)

    json.dumps(payload, ensure_ascii=False)
    json.dumps(result, ensure_ascii=False)


def test_cli_template_default_mock_does_not_call_openrouter(monkeypatch, capsys):
    monkeypatch.setattr(save_selected_article_draft, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(save_selected_article_draft, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        save_selected_article_draft,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(save_selected_article_draft, "build_gateway", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("template must not build gateway")))

    exit_code = save_selected_article_draft.main(["--topic-id", "9", "--candidate", "template", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider"] == "mock"
    assert payload["candidate_type"] == "template"
    assert payload["selected"]["draft"]["status"] == "pending_review"
    assert payload["summary"]["would_publish"] is False


def test_cli_llm_builds_gateway_only_for_llm(monkeypatch, capsys):
    gateway = FakeGateway()
    monkeypatch.setattr(save_selected_article_draft, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(save_selected_article_draft, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        save_selected_article_draft,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(save_selected_article_draft, "build_gateway", lambda provider, source_bundle: gateway)

    exit_code = save_selected_article_draft.main(["--topic-id", "9", "--candidate", "llm", "--provider", "mock", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert gateway.calls == 1
    assert payload["candidate_type"] == "llm"


def test_no_notion_or_publish_fields_in_outputs():
    payload = _saveable_payload("template")
    dumped = json.dumps(payload, ensure_ascii=False).lower()

    assert "notion" not in dumped
    assert payload["selected_draft"]["status"] != "approved"
    assert payload["selected_draft"]["status"] != "published"
    assert payload["summary"]["would_publish"] is False
