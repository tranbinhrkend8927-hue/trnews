import json
import sys
import types

from news_pipeline import article_review
from news_pipeline import review_article


def _body():
    return "\n\n".join(
        [
            "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia.",
            "Apa yang terjadi?\nBerdasarkan sumber berita yang tersimpan, pasar mencermati Rupiah dan Dolar AS.",
            "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami hubungan Rupiah, Dolar AS, The Fed, dan Bank Indonesia.",
            "Faktor yang perlu dipantau\n- Sentimen Dolar AS.\n- Kebijakan Bank Indonesia.\n- Agenda ekonomi global.",
            "Apa dampaknya bagi pembaca Indonesia?\nPembaca dapat memahami konteks pasar tanpa menganggap arah pasar sebagai hal yang sudah tentu.",
            "FAQ\nQ: Apakah ini saran trading?\nA: Tidak, ini informasi umum.",
            "Sumber\nSource news ID 10: Rupiah bergerak terhadap Dolar AS\nURL: https://example.com/source-10",
            "Catatan risiko: Artikel ini bersifat informasi umum dan bukan rekomendasi investasi, ajakan beli atau jual, maupun saran trading. Keputusan finansial tetap memerlukan pertimbangan pribadi dan sumber resmi.",
        ]
    )


def _article(**overrides):
    article = {
        "id": 1,
        "topic_id": 5,
        "symbol": "USDIDR",
        "language": "id",
        "title": "USD/IDR Hari Ini: Rupiah Bergerak, Ini Faktor yang Perlu Dipantau",
        "slug": "usd-idr-hari-ini-5",
        "summary": "Ringkasan USD/IDR untuk pembaca Indonesia dengan sumber berita tersimpan.",
        "body": _body(),
        "seo_title": "USD/IDR Hari Ini: Rupiah Bergerak",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia.",
        "status": "pending_review",
        "fact_check_status": "pending",
        "risk_disclaimer_included": True,
        "sources_json": {
            "topic_id": 5,
            "topic_type": "daily_usdidr_update",
            "symbol": "USDIDR",
            "source_news_ids": [10],
            "sources": [
                {
                    "news_id": 10,
                    "title": "Rupiah bergerak terhadap Dolar AS",
                    "url": "https://example.com/source-10",
                    "source": "Example News",
                }
            ],
            "missing_source_news_ids": [],
        },
        "published_at": None,
    }
    article.update(overrides)
    return article


def _article_sources():
    return [
        {
            "id": 100,
            "article_id": 1,
            "source_type": "forex_news",
            "source_name": "Example News",
            "source_url": "https://example.com/source-10",
            "cited_claim": "Rupiah bergerak terhadap Dolar AS",
        }
    ]


def _install_fake_psycopg(monkeypatch, connection):
    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda *args, **kwargs: connection
    psycopg_rows_module = types.ModuleType("psycopg.rows")
    psycopg_rows_module.dict_row = object()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", psycopg_rows_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)


def _check_codes(items):
    return {item["code"] for item in items}


def test_build_article_review_report_is_json_serializable_and_contains_results():
    report = article_review.build_article_review_report(_article(), _article_sources())

    dumped = json.dumps(report, ensure_ascii=False)

    assert report["article_id"] == 1
    assert report["source_count"] == 1
    assert report["has_sources"] is True
    assert report["has_risk_disclaimer"] is True
    assert "safety_result" in report
    assert "quality_result" in report
    assert "can_approve" in dumped


def test_good_pending_review_article_can_be_approved():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "approved")

    assert report["can_approve"] is True
    assert validation["valid"] is True
    assert validation["new_status"] == "approved"
    assert validation["new_status"] != "published"


def test_rejected_decision_maps_to_rejected_status():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "rejected", reviewer_notes="Unsupported claims")

    assert validation["valid"] is True
    assert validation["new_status"] == "rejected"


def test_needs_changes_decision_maps_to_pending_review_status():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "needs_changes", reviewer_notes="Need more sources")

    assert validation["valid"] is True
    assert validation["new_status"] == "pending_review"


def test_published_article_cannot_be_review_modified():
    report = article_review.build_article_review_report(_article(status="published"), _article_sources())
    validation = article_review.validate_review_decision(report, "rejected", reviewer_notes="Already live")

    assert validation["valid"] is False
    assert "article_published" in _check_codes(validation["errors"])


def test_fact_check_failed_cannot_be_approved():
    report = article_review.build_article_review_report(_article(fact_check_status="failed"), _article_sources())
    validation = article_review.validate_review_decision(report, "approved")

    assert validation["valid"] is False
    assert "fact_check_failed" in _check_codes(validation["errors"])


def test_fact_check_needs_sources_cannot_be_approved():
    report = article_review.build_article_review_report(_article(fact_check_status="needs_sources"), _article_sources())
    validation = article_review.validate_review_decision(report, "approved")

    assert validation["valid"] is False
    assert "fact_check_needs_sources" in _check_codes(validation["errors"])


def test_quality_blocked_cannot_be_approved():
    report = article_review.build_article_review_report(_article(), _article_sources())
    report["quality_result"]["level"] = "blocked"
    report["quality_result"]["blocking_issues"] = [{"name": "has_body", "severity": "error"}]
    report["approval_blockers"] = [
        {"code": "quality_blocked", "message": "Quality gate level is blocked."}
    ]
    report["can_approve"] = False
    validation = article_review.validate_review_decision(report, "approved")

    assert validation["valid"] is False
    assert "quality_blocked" in _check_codes(validation["errors"])


def test_safety_failed_cannot_be_approved():
    report = article_review.build_article_review_report(
        _article(body=_body() + "\nStrategi ini dijamin profit."),
        _article_sources(),
    )
    validation = article_review.validate_review_decision(report, "approved")

    assert validation["valid"] is False
    assert "safety_failed" in _check_codes(validation["errors"])


def test_missing_source_cannot_be_approved():
    article = _article(sources_json={"source_news_ids": [], "sources": []})
    report = article_review.build_article_review_report(article, [])
    validation = article_review.validate_review_decision(report, "approved")

    assert report["has_sources"] is False
    assert validation["valid"] is False
    assert "missing_sources" in _check_codes(validation["errors"])


def test_invalid_decision_returns_structured_error():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "publish")

    assert validation["valid"] is False
    assert validation["errors"][0]["code"] == "invalid_decision"


def test_rejected_without_notes_warns_but_allows():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "rejected")

    assert validation["valid"] is True
    assert validation["warnings"][0]["code"] == "reviewer_notes_recommended"


def test_needs_changes_without_notes_warns_but_allows():
    report = article_review.build_article_review_report(_article(), _article_sources())
    validation = article_review.validate_review_decision(report, "needs_changes")

    assert validation["valid"] is True
    assert validation["warnings"][0]["code"] == "reviewer_notes_recommended"


def test_decision_never_produces_published():
    report = article_review.build_article_review_report(_article(), _article_sources())
    for decision in ("approved", "rejected", "needs_changes"):
        validation = article_review.validate_review_decision(report, decision, reviewer_notes="Reviewed")
        assert validation["new_status"] != "published"


def test_reviewer_notes_are_json_safe():
    result = article_review.json_safe({"reviewer_notes": "Catatan aman: sumber sudah dicek."})

    dumped = json.dumps(result, ensure_ascii=False)

    assert "Catatan aman" in dumped


def test_dry_run_does_not_write_review_or_update_article(monkeypatch):
    calls = {"insert_review": 0, "update_article": 0}

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None
            self.next_fetchall = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            if "FROM generated_articles" in normalized:
                self.next_fetchone = _article()
                return
            if "FROM article_sources" in normalized:
                self.next_fetchall = _article_sources()
                return
            if "INSERT INTO article_reviews" in normalized:
                calls["insert_review"] += 1
                return
            if "UPDATE generated_articles" in normalized:
                calls["update_article"] += 1
                return
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

        def fetchall(self):
            return self.next_fetchall

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_review.save_article_review_to_postgres(
        "postgresql://example/db",
        1,
        "approved",
        reviewer="editor",
        reviewer_notes="Reviewed sources",
        dry_run=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["summary"]["would_insert"] == 1
    assert calls == {"insert_review": 0, "update_article": 0}


def test_save_db_writes_review_and_updates_article_status(monkeypatch):
    calls = {"insert_review": 0, "update_article": 0, "status": None}

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None
            self.next_fetchall = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                return
            if "FROM generated_articles" in normalized:
                self.next_fetchone = _article()
                return
            if "FROM article_sources" in normalized:
                self.next_fetchall = _article_sources()
                return
            if "INSERT INTO article_reviews" in normalized:
                calls["insert_review"] += 1
                self.next_fetchone = {"id": 9}
                return
            if "UPDATE generated_articles" in normalized:
                calls["update_article"] += 1
                calls["status"] = params[0]
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

        def fetchall(self):
            return self.next_fetchall

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_review.save_article_review_to_postgres(
        "postgresql://example/db",
        1,
        "approved",
        reviewer="editor",
        reviewer_notes="Reviewed sources",
    )

    assert result["success"] is True
    assert result["review_id"] == 9
    assert result["new_status"] == "approved"
    assert result["new_status"] != "published"
    assert result["summary"]["reviews_inserted"] == 1
    assert result["summary"]["articles_updated"] == 1
    assert calls == {"insert_review": 1, "update_article": 1, "status": "approved"}


def test_save_db_rejected_updates_status_to_rejected(monkeypatch):
    statuses = []

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None
            self.next_fetchall = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                return
            if "FROM generated_articles" in normalized:
                self.next_fetchone = _article()
                return
            if "FROM article_sources" in normalized:
                self.next_fetchall = _article_sources()
                return
            if "INSERT INTO article_reviews" in normalized:
                self.next_fetchone = (11,)
                return
            if "UPDATE generated_articles" in normalized:
                statuses.append(params[0])
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

        def fetchall(self):
            return self.next_fetchall

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_review.save_article_review_to_postgres(
        "postgresql://example/db",
        1,
        "rejected",
        reviewer_notes="Unsupported claims",
    )

    assert result["success"] is True
    assert statuses == ["rejected"]


def test_save_db_needs_changes_updates_status_to_pending_review(monkeypatch):
    statuses = []

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None
            self.next_fetchall = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                return
            if "FROM generated_articles" in normalized:
                self.next_fetchone = _article()
                return
            if "FROM article_sources" in normalized:
                self.next_fetchall = _article_sources()
                return
            if "INSERT INTO article_reviews" in normalized:
                self.next_fetchone = (12,)
                return
            if "UPDATE generated_articles" in normalized:
                statuses.append(params[0])
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

        def fetchall(self):
            return self.next_fetchall

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_review.save_article_review_to_postgres(
        "postgresql://example/db",
        1,
        "needs_changes",
        reviewer_notes="Need more sources",
    )

    assert result["success"] is True
    assert statuses == ["pending_review"]


def test_published_article_save_db_does_not_insert_or_update(monkeypatch):
    calls = {"insert_review": 0, "update_article": 0}

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            if "FROM generated_articles" in normalized:
                self.next_fetchone = _article(status="published")
                return
            if "INSERT INTO article_reviews" in normalized:
                calls["insert_review"] += 1
                return
            if "UPDATE generated_articles" in normalized:
                calls["update_article"] += 1
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
            pass

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_review.save_article_review_to_postgres(
        "postgresql://example/db",
        1,
        "rejected",
        reviewer_notes="Already live",
    )

    assert result["success"] is False
    assert result["errors"][0]["code"] == "article_published"
    assert calls == {"insert_review": 0, "update_article": 0}


def test_cli_report_outputs_review_report(monkeypatch, capsys):
    monkeypatch.setattr(review_article, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(review_article, "fetch_article_for_review", lambda dsn, article_id: _article(id=article_id))
    monkeypatch.setattr(review_article, "fetch_article_sources_for_review", lambda dsn, article_id: _article_sources())

    exit_code = review_article.main(["--article-id", "1", "--report"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["report"]["article_id"] == 1
    assert "safety_result" in payload["report"]
    assert "quality_result" in payload["report"]


def test_cli_dry_run_outputs_structured_review(monkeypatch, capsys):
    monkeypatch.setattr(review_article, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(
        review_article,
        "save_article_review_to_postgres",
        lambda *args, **kwargs: {
            "success": True,
            "article_id": 1,
            "decision": "approved",
            "dry_run": True,
            "previous_status": "pending_review",
            "new_status": "approved",
            "review_report": {"article_id": 1},
            "validation": {"valid": True, "new_status": "approved"},
            "summary": {"reviews_inserted": 0, "articles_updated": 0},
            "errors": [],
        },
    )

    exit_code = review_article.main(["--article-id", "1", "--decision", "approved", "--reviewer", "editor", "--notes", "Reviewed", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["review"]["dry_run"] is True
    assert payload["review"]["new_status"] == "approved"
    assert payload["review"]["new_status"] != "published"


def test_cli_rejects_report_and_decision_together(capsys):
    exit_code = review_article.main(["--article-id", "1", "--report", "--decision", "approved"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"][0]["code"] == "ambiguous_mode"
