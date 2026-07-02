from src.writing.rewrite_engine import build_rewrite_plan, disabled_rewrite_plan, is_optional_rewrite_enabled


def test_optional_rewrite_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_OPTIONAL_REWRITE", raising=False)

    assert is_optional_rewrite_enabled() is False
    assert disabled_rewrite_plan().enabled is False


def test_rewrite_plan_not_needed_without_signals():
    plan = build_rewrite_plan(article={"title": "A"}, ai_review=None, article_quality_report=None, validation={})

    assert plan.enabled is True
    assert plan.status == "not_needed"
    assert plan.should_rewrite is False


def test_rewrite_plan_suggests_edits_from_ai_review():
    plan = build_rewrite_plan(
        article={"title": "A"},
        ai_review={
            "publish_readiness": "needs_edit",
            "unsupported_claims": ["Unsupported macro claim"],
            "overstatements": ["USD must rise"],
            "missing_context": ["No central bank context"],
            "rewrite_suggestions": ["Add source-backed context."],
        },
        article_quality_report={"final_recommended_status": "needs_edit", "warnings": ["thin_context"]},
        validation={},
    )

    assert plan.status == "suggested"
    assert plan.should_rewrite is True
    assert plan.automatic_rewrite_performed is False
    assert {action.action_type for action in plan.actions} >= {
        "remove_or_source_claim",
        "soften_overstatement",
        "add_context",
        "reviewer_suggestion",
    }


def test_rewrite_plan_blocks_rejected_or_validator_failed_drafts():
    plan = build_rewrite_plan(
        article={"title": "A"},
        ai_review={"publish_readiness": "reject"},
        article_quality_report={"final_recommended_status": "rejected"},
        validation={"financial_safety": {"passed": False}},
    )

    assert plan.status == "blocked"
    assert any(action.action_type == "reject_or_rebuild" for action in plan.actions)
    assert any(action.action_type == "validator_failure" for action in plan.actions)
