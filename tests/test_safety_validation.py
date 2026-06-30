import json

import article_templates
import safety_validation


def _article(**overrides):
    article = {
        "title": "USD/IDR Hari Ini",
        "summary": "",
        "body": "",
        "seo_title": "",
        "seo_description": "",
        "status": "draft",
        "fact_check_status": "pending",
        "risk_disclaimer_included": True,
        "sources_json": {"source_news_ids": [1]},
    }
    article.update(overrides)
    return article


def test_blocks_dijamin_profit():
    result = safety_validation.validate_financial_safety(_article(body="Strategi ini dijamin profit."))

    assert result["passed"] is False
    assert result["fact_check_status"] == "failed"
    assert result["violations"][0]["type"] == "profit_promise"


def test_blocks_pasti_untung():
    result = safety_validation.validate_financial_safety(_article(summary="Pembaca pasti untung."))

    assert result["passed"] is False
    assert result["fact_check_status"] == "failed"
    assert result["violations"][0]["matches"] == ["pasti untung"]


def test_blocks_buy_sell_instructions():
    buy = safety_validation.validate_financial_safety(_article(title="Beli sekarang USD/IDR"))
    sell = safety_validation.validate_financial_safety(_article(seo_description="Jual sekarang saat rupiah bergerak"))

    assert buy["fact_check_status"] == "failed"
    assert sell["fact_check_status"] == "failed"
    assert buy["violations"][0]["type"] == "buy_sell_instruction"


def test_blocks_take_profit_stop_loss_phrases():
    article = _article(body="Take profit di level ini dan stop loss ketat. TP di atas, SL di bawah.")

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "failed"
    assert any(item["type"] == "take_profit_stop_loss" for item in result["violations"])


def test_checks_title_summary_body_and_seo_fields():
    fields = ["title", "summary", "body", "seo_title", "seo_description"]
    for field in fields:
        article = _article(**{field: "Guaranteed profit untuk USD/IDR"})
        result = safety_validation.validate_financial_safety(article)
        assert result["fact_check_status"] == "failed"


def test_financial_terms_without_sources_need_sources():
    article = _article(title="CPI dan Bank Indonesia mempengaruhi rupiah", sources_json={})

    result = safety_validation.validate_financial_safety(article)

    assert result["passed"] is False
    assert result["fact_check_status"] == "needs_sources"
    assert any(item["type"] == "missing_sources_for_financial_terms" for item in result["violations"])


def test_clean_draft_with_sources_and_risk_disclaimer_passes_basic_validation():
    article = _article(title="Market update", summary="General context without restricted terms.")

    result = safety_validation.validate_financial_safety(article)

    assert result["passed"] is True
    assert result["violations"] == []
    assert result["fact_check_status"] == "pending"


def test_missing_risk_disclaimer_is_reported():
    article = _article(title="Market update", risk_disclaimer_included=False)

    result = safety_validation.validate_financial_safety(article)

    assert result["passed"] is False
    assert any(item["type"] == "missing_risk_disclaimer" for item in result["violations"])


def test_apply_fact_check_status_does_not_publish_article_or_mutate_input():
    article = _article(status="draft", body="dijamin profit")
    result = safety_validation.validate_financial_safety(article)

    updated = safety_validation.apply_fact_check_status(article, result)

    assert updated["fact_check_status"] == "failed"
    assert updated["status"] == "draft"
    assert article["fact_check_status"] == "pending"


def test_apply_fact_check_status_never_keeps_published_status():
    article = _article(status="published", title="CPI tanpa sumber", sources_json={})
    result = safety_validation.validate_financial_safety(article)

    updated = safety_validation.apply_fact_check_status(article, result)

    assert updated["status"] == "pending_review"
    assert updated["status"] != "published"


def test_validation_result_is_json_serializable():
    result = safety_validation.validate_financial_safety(_article(title="NFP dan The Fed", sources_json={}))

    dumped = json.dumps(result, ensure_ascii=False)

    assert "needs_sources" in dumped


def test_template_content_passes_blocked_phrase_checks_with_sources():
    rendered = article_templates.render_article_template(
        {
            "id": 1,
            "symbol": "USDIDR",
            "topic_type": "daily_usdidr_update",
            "status": "candidate",
            "reason_json": {"source_news_ids": [1]},
            "source_news_ids": [1],
        }
    )
    article = _article(
        title=rendered["title"],
        summary=rendered["summary"],
        body=rendered["body"],
        seo_title=rendered["seo_title"],
        seo_description=rendered["seo_description"],
        risk_disclaimer_included=rendered["risk_disclaimer_included"],
        sources_json=rendered["sources_json"],
    )

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "pending"
    assert not any(
        item["type"] in {"profit_promise", "buy_sell_instruction", "take_profit_stop_loss"}
        for item in result["violations"]
    )


def test_template_content_without_sources_needs_sources():
    rendered = article_templates.render_article_template(
        {
            "id": 1,
            "symbol": "USDIDR",
            "topic_type": "macro_event_watch",
            "status": "candidate",
            "reason_json": {},
            "source_news_ids": [],
        }
    )
    article = _article(
        title=rendered["title"],
        summary=rendered["summary"],
        body=rendered["body"],
        risk_disclaimer_included=True,
        sources_json=rendered["sources_json"],
    )

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "needs_sources"
    assert any(item["type"] == "missing_sources_for_financial_terms" for item in result["violations"])


def test_template_content_with_sources_and_disclaimer_is_not_failed():
    rendered = article_templates.render_article_template(
        {
            "id": 1,
            "symbol": "USDIDR",
            "topic_type": "rupiah_explainer",
            "status": "candidate",
            "reason_json": {"source_news_ids": [8]},
            "source_news_ids": [8],
        }
    )
    article = _article(
        title=rendered["title"],
        summary=rendered["summary"],
        body=rendered["body"],
        risk_disclaimer_included=True,
        sources_json=rendered["sources_json"],
    )

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] != "failed"
    assert result["passed"] is True


def test_sources_json_sources_are_recognized_as_sources():
    article = _article(
        title="USD/IDR dan Rupiah menjadi perhatian",
        sources_json={
            "source_news_ids": [],
            "sources": [{"news_id": 9, "title": "Rupiah source", "url": None}],
        },
    )

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "pending"
    assert result["passed"] is True


def test_no_sources_still_needs_sources_for_financial_terms():
    article = _article(title="USD/IDR dan The Fed menjadi perhatian", sources_json={"sources": []})

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "needs_sources"


def test_blocked_phrase_still_fails_when_sources_exist():
    article = _article(
        title="USD/IDR",
        body="Konten ini dijamin profit.",
        sources_json={"sources": [{"news_id": 9, "title": "Source"}]},
    )

    result = safety_validation.validate_financial_safety(article)

    assert result["fact_check_status"] == "failed"
    assert any(item["type"] == "profit_promise" for item in result["violations"])
