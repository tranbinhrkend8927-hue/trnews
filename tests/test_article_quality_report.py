from src.models.quality import ArticleQualityReport
from src.review.quality_report import build_article_quality_report
from tests.test_article_schema import valid_article


RISK_DISCLAIMER = "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."


def _article(**overrides):
    article = valid_article(risk_disclaimer=RISK_DISCLAIMER)
    article["body"] = "\n\n".join(
        [
            "Ikhtisar peristiwa\nUSD/IDR bergerak berdasarkan sumber yang tersedia.",
            "Latar belakang\nBank sentral, data ekonomi, inflasi, dan sentimen risiko perlu diperhatikan.",
            "Dampak pasar\nImplikasi pasar harus dibaca hati-hati tanpa menyimpulkan arah harga.",
            "Sumber\nhttps://example.com/source-1",
            f"Catatan risiko\n{RISK_DISCLAIMER}",
        ]
    )
    article.update(overrides)
    return article


def _source_bundle(**overrides):
    bundle = {
        "sources": [{"source_id": "source-1", "url": "https://example.com/source-1"}],
        "source_quality_report": {
            "source_count": 2,
            "usable_source_count": 2,
            "overall_source_quality": "strong",
            "recommended_action": "write_article",
        },
    }
    bundle.update(overrides)
    return bundle


def _validation(**overrides):
    validation = {
        "article_schema": {"passed": True, "issues": []},
        "source_grounding": {"passed": True, "issues": []},
        "financial_safety": {"passed": True, "issues": []},
        "depth_quality": {"passed": True, "issues": []},
    }
    validation.update(overrides)
    return validation


def _ai_review(**overrides):
    review = {
        "publish_readiness": "ready",
        "scores": {
            "grounding": 90,
            "depth": 88,
            "readability": 85,
            "headline_quality": 88,
            "financial_safety": 95,
            "source_usefulness": 90,
        },
        "issues": [],
        "unsupported_claims": [],
        "overstatements": [],
        "missing_context": [],
    }
    review.update(overrides)
    return review


def test_article_quality_report_ready_case():
    report = build_article_quality_report(
        article=_article(),
        source_bundle=_source_bundle(),
        validation=_validation(),
        ai_review=_ai_review(),
    )

    assert report.final_recommended_status == "needs_review"
    assert report.editor_ready_score >= 75
    assert report.source_count == 2
    assert report.usable_source_count == 2
    assert report.has_market_context is True
    assert report.has_risk_disclaimer is True
    assert report.has_source_attribution is True
    assert report.grounded_claim_ratio == 1.0
    assert report.headline_risk_level == "low"


def test_article_quality_report_needs_edit_from_ai_review():
    report = build_article_quality_report(
        article=_article(),
        source_bundle=_source_bundle(),
        validation=_validation(),
        ai_review=_ai_review(
            publish_readiness="needs_edit",
            scores={
                "grounding": 70,
                "depth": 65,
                "readability": 80,
                "headline_quality": 75,
                "financial_safety": 90,
                "source_usefulness": 70,
            },
            missing_context=["Needs more market context."],
        ),
    )

    assert report.final_recommended_status == "needs_edit"
    assert report.editor_ready_score < 75
    assert any("Needs more market context" in warning for warning in report.warnings)


def test_article_quality_report_rejects_financial_safety_issue():
    report = build_article_quality_report(
        article=_article(),
        source_bundle=_source_bundle(),
        validation=_validation(
            financial_safety={
                "passed": False,
                "issues": [{"severity": "error", "code": "buy_sell_instruction", "message": "Buy now", "field": "body"}],
            }
        ),
        ai_review=_ai_review(publish_readiness="reject"),
    )

    assert report.final_recommended_status == "rejected"
    assert report.financial_advice_detected is True
    assert report.editor_ready_score <= 25
    assert any("financial_safety" in issue for issue in report.blocking_issues)


def test_article_quality_report_source_insufficient_needs_rewrite():
    report = build_article_quality_report(
        article=_article(),
        source_bundle=_source_bundle(
            source_quality_report={
                "source_count": 1,
                "usable_source_count": 0,
                "overall_source_quality": "insufficient",
                "recommended_action": "skip_or_manual_review",
            }
        ),
        validation=_validation(),
        ai_review={},
    )

    assert report.final_recommended_status == "needs_rewrite"
    assert "source_quality: skip_or_manual_review" in report.blocking_issues
    assert report.editor_ready_score < 75


def test_article_quality_report_headline_risk_from_title():
    report = build_article_quality_report(
        article=_article(title="USD/IDR pasti naik setelah berita terbaru"),
        source_bundle=_source_bundle(),
        validation=_validation(),
        ai_review={},
    )

    assert report.headline_risk_level == "high"


def test_article_quality_report_clamps_scores():
    report = ArticleQualityReport(editor_ready_score=200, grounded_claim_ratio=2.0)

    assert report.editor_ready_score == 100
    assert report.grounded_claim_ratio == 1.0
