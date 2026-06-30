import json

from news_pipeline import draft_quality


def _source_bundle(**overrides):
    bundle = {
        "topic_id": 1,
        "topic_type": "daily_usdidr_update",
        "symbol": "USDIDR",
        "source_news_ids": [1],
        "sources": [
            {
                "news_id": 1,
                "title": "Rupiah bergerak terhadap Dolar AS",
                "url": "https://example.com/rupiah",
                "source": "Example News",
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
    }
    bundle.update(overrides)
    return bundle


def _draft(**overrides):
    body = "\n\n".join(
        [
            "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia.",
            "Apa yang terjadi?\nBerdasarkan sumber berita yang tersimpan, pasar mencermati Rupiah dan Dolar AS.",
            "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami hubungan Rupiah, Dolar AS, The Fed, dan Bank Indonesia.",
            "Faktor yang perlu dipantau\n- Sentimen Dolar AS.\n- Kebijakan Bank Indonesia.\n- Agenda ekonomi global.",
            "Apa dampaknya bagi pembaca Indonesia?\nPembaca dapat memahami konteks pasar tanpa menganggap arah pasar sebagai hal yang sudah tentu.",
            "FAQ\nQ: Apakah ini saran trading?\nA: Tidak, ini informasi umum.",
            "Sumber\nSource news ID 1: Rupiah bergerak terhadap Dolar AS\nURL: https://example.com/rupiah",
            "Catatan risiko: Artikel ini bersifat informasi umum dan bukan rekomendasi investasi, ajakan beli atau jual, maupun saran trading. Keputusan finansial tetap memerlukan pertimbangan pribadi dan sumber resmi.",
        ]
    )
    draft = {
        "title": "USD/IDR Hari Ini: Rupiah Bergerak, Ini Faktor yang Perlu Dipantau",
        "summary": "Ringkasan USD/IDR untuk pembaca Indonesia dengan sumber berita tersimpan.",
        "body": body,
        "seo_title": "USD/IDR Hari Ini: Rupiah Bergerak",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia.",
        "slug": "usd-idr-hari-ini-1",
        "status": "pending_review",
        "fact_check_status": "pending",
        "risk_disclaimer_included": True,
        "sources_json": _source_bundle(),
    }
    draft.update(overrides)
    return draft


def _safety(**overrides):
    result = {"passed": True, "violations": [], "fact_check_status": "pending"}
    result.update(overrides)
    return result


def _check_names(result, collection):
    return {item["name"] for item in result[collection]}


def test_good_draft_returns_ready_for_review_or_needs_review():
    result = draft_quality.evaluate_draft_quality(_draft(), source_bundle=_source_bundle(), safety_result=_safety())

    assert result["passed"] is True
    assert result["level"] in {"ready_for_review", "needs_review"}
    assert result["recommendation"] == "pending_review"


def test_missing_title_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(title=""), source_bundle=_source_bundle(), safety_result=_safety())

    assert result["passed"] is False
    assert "has_title" in _check_names(result, "blocking_issues")


def test_missing_body_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(body=""), source_bundle=_source_bundle(), safety_result=_safety())

    assert "has_body" in _check_names(result, "blocking_issues")


def test_missing_summary_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(summary=""), source_bundle=_source_bundle(), safety_result=_safety())

    assert "has_summary" in _check_names(result, "blocking_issues")


def test_published_status_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(status="published"), source_bundle=_source_bundle(), safety_result=_safety())

    assert "not_published_or_approved" in _check_names(result, "blocking_issues")
    assert result["recommendation"] == "needs_rework"


def test_approved_status_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(status="approved"), source_bundle=_source_bundle(), safety_result=_safety())

    assert "not_published_or_approved" in _check_names(result, "blocking_issues")


def test_safety_failed_blocks():
    safety = _safety(passed=False, violations=[{"type": "profit_promise"}], fact_check_status="failed")

    result = draft_quality.evaluate_draft_quality(_draft(fact_check_status="failed"), source_bundle=_source_bundle(), safety_result=safety)

    assert "safety_has_no_blocked_phrase_violation" in _check_names(result, "blocking_issues")


def test_fact_check_status_failed_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(fact_check_status="failed"), source_bundle=_source_bundle(), safety_result=_safety())

    assert "fact_check_not_failed" in _check_names(result, "blocking_issues")


def test_missing_risk_disclaimer_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(risk_disclaimer_included=False), source_bundle=_source_bundle(), safety_result=_safety())

    assert "has_risk_disclaimer_flag" in _check_names(result, "blocking_issues")


def test_missing_sumber_section_blocks():
    draft = _draft(body=_draft()["body"].replace("Sumber", "Referensi"))

    result = draft_quality.evaluate_draft_quality(draft, source_bundle=_source_bundle(), safety_result=_safety())

    assert "body_has_source_section" in _check_names(result, "blocking_issues")


def test_missing_catatan_risiko_section_blocks():
    draft = _draft(body=_draft()["body"].replace("Catatan risiko", "Catatan umum"))

    result = draft_quality.evaluate_draft_quality(draft, source_bundle=_source_bundle(), safety_result=_safety())

    assert "body_has_risk_disclaimer_section" in _check_names(result, "blocking_issues")


def test_no_sources_with_financial_terms_blocks():
    result = draft_quality.evaluate_draft_quality(_draft(), source_bundle=_source_bundle(sources=[]), safety_result=_safety())

    assert "financial_terms_have_sources" in _check_names(result, "blocking_issues")


def test_source_count_zero_warning():
    result = draft_quality.evaluate_draft_quality(
        _draft(title="Market context", summary="General summary for review.", body="Sumber\nCatatan risiko\nFAQ\n" + "A" * 600),
        source_bundle=_source_bundle(sources=[]),
        safety_result=_safety(),
    )

    assert "has_sources" in _check_names(result, "warnings")
    assert result["metadata"]["source_count"] == 0


def test_missing_source_news_ids_warning():
    result = draft_quality.evaluate_draft_quality(
        _draft(),
        source_bundle=_source_bundle(missing_source_news_ids=[2]),
        safety_result=_safety(),
    )

    assert "no_missing_source_news_ids" in _check_names(result, "warnings")


def test_needs_sources_warning():
    result = draft_quality.evaluate_draft_quality(
        _draft(fact_check_status="needs_sources"),
        source_bundle=_source_bundle(),
        safety_result=_safety(fact_check_status="needs_sources"),
    )

    assert "fact_check_not_needs_sources" in _check_names(result, "warnings")


def test_faq_missing_warning():
    draft = _draft(body=_draft()["body"].replace("FAQ", "Pertanyaan umum"))

    result = draft_quality.evaluate_draft_quality(draft, source_bundle=_source_bundle(), safety_result=_safety())

    assert "has_faq" in _check_names(result, "warnings")


def test_score_clamps_between_zero_and_one_hundred():
    bad = _draft(
        title="",
        summary="",
        body="",
        status="published",
        fact_check_status="failed",
        risk_disclaimer_included=False,
        seo_title="",
        seo_description="",
        slug="",
    )

    bad_result = draft_quality.evaluate_draft_quality(bad, source_bundle=_source_bundle(sources=[]), safety_result=_safety(fact_check_status="failed"))
    good_result = draft_quality.evaluate_draft_quality(_draft(), source_bundle=_source_bundle(), safety_result=_safety())

    assert 0 <= bad_result["score"] <= 100
    assert 0 <= good_result["score"] <= 100


def test_recommendation_never_returns_approved_or_published():
    for draft in (_draft(), _draft(status="published")):
        result = draft_quality.evaluate_draft_quality(draft, source_bundle=_source_bundle(), safety_result=_safety())
        assert result["recommendation"] not in {"approved", "published"}


def test_result_is_json_serializable():
    result = draft_quality.evaluate_draft_quality(_draft(), source_bundle=_source_bundle(), safety_result=_safety())

    dumped = json.dumps(result, ensure_ascii=False)

    assert "recommendation" in dumped


def test_blocked_phrase_in_draft_blocks_even_without_safety_result():
    result = draft_quality.evaluate_draft_quality(
        _draft(body=_draft()["body"] + "\nStrategi ini dijamin profit."),
        source_bundle=_source_bundle(),
        safety_result=_safety(),
    )

    assert "no_blocked_phrases" in _check_names(result, "blocking_issues")
