from copy import deepcopy

from src.llm.result import LLMTaskError, LLMTaskResult
from src.review.article_reviewer import is_ai_reviewer_enabled, is_llm_ai_reviewer_enabled, review_article, review_article_deterministic
from tests.test_article_schema import valid_article


RISK_DISCLAIMER = "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."


def _article(**overrides):
    article = valid_article(risk_disclaimer=RISK_DISCLAIMER)
    article["body"] = "\n\n".join(
        [
            "Ikhtisar peristiwa\nUSD/IDR bergerak setelah berita dari sumber utama yang tersedia.",
            "Latar belakang\nPergerakan pasangan ini perlu dibaca bersama data ekonomi dan sentimen risiko.",
            "Dampak pasar\nSumber membantu pembaca memahami konteks tanpa menyimpulkan arah harga secara pasti.",
            "Hal yang perlu dipantau\nPantau data ekonomi lanjutan dan komunikasi bank sentral.",
            "FAQ\nApa yang perlu dipantau? Data ekonomi lanjutan dan sentimen risiko.",
            "Sumber\nhttps://example.com/source-1",
            f"Catatan risiko\n{RISK_DISCLAIMER}",
        ]
    )
    article.update(overrides)
    return article


def _source_bundle(**overrides):
    bundle = {
        "sources": [{"source_id": "source-1", "url": "https://example.com/source-1", "title": "USD/IDR source"}],
        "source_quality_report": {
            "overall_source_quality": "strong",
            "recommended_action": "write_article",
            "usable_source_count": 2,
            "source_gaps": [],
        },
    }
    bundle.update(overrides)
    return bundle


def _brief(**overrides):
    brief = {
        "content_type": "deep_article",
        "confidence_level": "high",
        "source_gaps": [],
        "primary_angle": "Explain the source event without trading advice.",
    }
    brief.update(overrides)
    return brief


def test_review_ready_case():
    review = review_article_deterministic(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
    )

    assert review.publish_readiness == "ready"
    assert review.scores.grounding >= 75
    assert review.issues == []
    assert review.reviewer_mode == "deterministic"


def test_unsupported_claims_cannot_be_ready():
    validation = {
        "source_grounding": {
            "passed": False,
            "issues": [{"severity": "error", "message": "Unknown source URL: https://bad.example", "field": "body"}],
        }
    }
    review = review_article_deterministic(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation=validation,
    )

    assert review.publish_readiness == "needs_edit"
    assert review.unsupported_claims
    assert any(issue.issue_type == "unsupported_claim" for issue in review.issues)


def test_financial_safety_issue_rejects_by_default():
    validation = {
        "financial_safety": {
            "passed": False,
            "issues": [{"severity": "error", "message": "Article contains buy/sell instruction language.", "field": "body"}],
        }
    }
    review = review_article_deterministic(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation=validation,
    )

    assert review.publish_readiness == "reject"
    assert review.scores.financial_safety < 75
    assert any(issue.issue_type == "financial_safety" for issue in review.issues)


def test_weak_source_quality_needs_edit():
    review = review_article_deterministic(
        article=_article(article_type="fx_news_explainer"),
        editorial_brief=_brief(content_type="market_brief", confidence_level="low", source_gaps=["not_enough_usable_sources_for_deep_article"]),
        source_bundle=_source_bundle(
            source_quality_report={
                "overall_source_quality": "weak",
                "recommended_action": "write_brief_only",
                "source_gaps": ["not_enough_usable_sources_for_deep_article"],
            }
        ),
        validation={},
    )

    assert review.publish_readiness == "needs_edit"
    assert any(issue.issue_type == "source_quality" for issue in review.issues)
    assert any(issue.issue_type == "brief_alignment" for issue in review.issues)
    assert review.missing_context


def test_overstatement_rejects():
    article = _article(title="USD/IDR pasti naik setelah berita terbaru")
    review = review_article_deterministic(
        article=article,
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
    )

    assert review.publish_readiness == "reject"
    assert review.overstatements
    assert any(issue.issue_type == "headline_quality" for issue in review.issues)


def test_reviewer_does_not_modify_article():
    article = _article()
    before = deepcopy(article)

    review_article_deterministic(
        article=article,
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
    )

    assert article == before


def test_ai_reviewer_flag_default_off(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_REVIEWER", raising=False)
    assert is_ai_reviewer_enabled() is False


def test_ai_reviewer_flag_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_REVIEWER", "1")
    assert is_ai_reviewer_enabled() is True


class _FakeReviewRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _llm_review_output(**overrides):
    output = {
        "publish_readiness": "needs_edit",
        "scores": {
            "grounding": 70,
            "depth": 68,
            "readability": 82,
            "headline_quality": 80,
            "financial_safety": 90,
            "source_usefulness": 75,
        },
        "issues": [
            {
                "issue_type": "depth",
                "severity": "medium",
                "location": "body",
                "description": "Article needs more source-backed context.",
                "suggested_fix": "Add context tied to the provided source bundle.",
            }
        ],
        "unsupported_claims": [],
        "overstatements": [],
        "missing_context": ["Needs more context."],
        "rewrite_suggestions": ["Add source-backed context."],
        "recommended_editor_action": "Send to editor with highlighted issues.",
    }
    output.update(overrides)
    return output


def test_llm_ai_reviewer_flag_default_off(monkeypatch):
    monkeypatch.delenv("ENABLE_LLM_AI_REVIEWER", raising=False)
    assert is_llm_ai_reviewer_enabled() is False


def test_review_article_uses_llm_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_AI_REVIEWER", "1")
    runner = _FakeReviewRunner(
        LLMTaskResult(
            success=True,
            task="article_review",
            language="id",
            profile="reviewer",
            output=_llm_review_output(),
        )
    )

    review = review_article(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
        language="id",
        language_profile={"language": "id"},
        llm_runner=runner,
        review_profile="reviewer",
    )

    assert review.reviewer_mode == "llm"
    assert review.publish_readiness == "needs_edit"
    assert runner.calls[0]["task"] == "article_review"
    assert runner.calls[0]["profile"] == "reviewer"
    assert runner.calls[0]["input_data"]["article"]["title"] == _article()["title"]


def test_review_article_falls_back_when_llm_result_fails(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_AI_REVIEWER", "1")
    runner = _FakeReviewRunner(
        LLMTaskResult(
            success=False,
            task="article_review",
            error=LLMTaskError(type="llm_failed", message="review model failed"),
        )
    )

    review = review_article(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
        language="id",
        language_profile={"language": "id"},
        llm_runner=runner,
        review_profile="reviewer",
    )

    assert review.reviewer_mode == "deterministic_fallback"
    assert review.publish_readiness == "ready"
    assert any(issue.issue_type == "reviewer_runtime" for issue in review.issues)


def test_review_article_falls_back_when_llm_output_is_invalid(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_AI_REVIEWER", "1")
    runner = _FakeReviewRunner(
        LLMTaskResult(
            success=True,
            task="article_review",
            output={"publish_readiness": "ready"},
        )
    )

    review = review_article(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
        language="id",
        language_profile={"language": "id"},
        llm_runner=runner,
        review_profile="reviewer",
    )

    assert review.reviewer_mode == "deterministic_fallback"
    assert any("AIReview validation" in issue.description for issue in review.issues)


def test_review_article_does_not_call_llm_when_llm_review_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_AI_REVIEWER", "0")
    runner = _FakeReviewRunner(LLMTaskResult(success=True, task="article_review", output=_llm_review_output()))

    review = review_article(
        article=_article(),
        editorial_brief=_brief(),
        source_bundle=_source_bundle(),
        validation={},
        language="id",
        language_profile={"language": "id"},
        llm_runner=runner,
        review_profile="reviewer",
    )

    assert review.reviewer_mode == "deterministic"
    assert runner.calls == []
