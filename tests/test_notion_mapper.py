from src.config.loader import load_config_registry
from src.notion.mapper import NotionBlockBuilder, NotionPropertyMapper
from src.notion.target_resolver import ResolvedNotionTarget
from tests.test_article_schema import valid_article


def _context(body=None):
    registry = load_config_registry()
    market = registry.pipeline.markets[0]
    language_profile = registry.languages["id"]
    article = valid_article(
        risk_disclaimer=language_profile.risk_disclaimer,
        body=body
        or (
            "Pembuka.\n\nSumber\nhttps://example.com/a\n\nCatatan risiko\n"
            + language_profile.risk_disclaimer
        ),
    )
    source_bundle = {"source_trace": {"source_count": 1}, "source_bundle_hash": "hash"}
    validation = {"article_schema": {"passed": True, "issues": []}}
    llm = {"prompt_version": "article_draft@unit+id", "model": "unit-model", "usage": {"total_tokens": 1}}
    target = ResolvedNotionTarget(
        name="notion_articles_id",
        language="id",
        market="Indonesia",
        parent_type="data_source",
        parent_id="ds",
        reviewer_status="Needs Review",
    )
    return article, market, language_profile, source_bundle, validation, llm, target


def test_properties_include_name_title():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target,
        content_job_key="job-key", source_bundle_hash="bundle-hash", pipeline_run_id="run-id"
    )

    assert props["Name"]["title"][0]["text"]["content"] == article["title"]


def test_status_uses_reviewer_status():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Status"]["status"]["name"] == "Needs Review"


def test_language_market_symbol_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Language"]["select"]["name"] == "id"
    assert props["Market"]["select"]["name"] == "Indonesia"
    assert props["Symbol"]["rich_text"][0]["text"]["content"] == "USDIDR"


def test_source_count_and_urls_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Source Count"]["number"] == 1
    assert "https://example.com/a" in props["Source URLs"]["rich_text"][0]["text"]["content"]


def test_editorial_seo_fields_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Search Intent"]["rich_text"][0]["text"]["content"] == article["search_intent"]
    assert props["Primary Keyword"]["rich_text"][0]["text"]["content"] == article["primary_keyword"]
    assert article["candidate_titles"][0] in props["Candidate Titles"]["rich_text"][0]["text"]["content"]


def test_structured_brief_properties_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    bundle["editorial_brief"] = {"content_type": "market_brief", "confidence_level": "low"}
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Brief Content Type"]["select"]["name"] == "market_brief"
    assert props["Brief Confidence"]["select"]["name"] == "low"


def test_source_quality_properties_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    bundle["source_quality_report"] = {
        "usable_source_count": 2,
        "overall_source_quality": "acceptable",
    }
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Usable Source Count"]["number"] == 2
    assert props["Source Quality"]["select"]["name"] == "acceptable"


def test_ai_review_properties_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    bundle["ai_review"] = {
        "publish_readiness": "needs_edit",
        "scores": {"grounding": 70, "depth": 65, "financial_safety": 90},
    }
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["AI Review Readiness"]["select"]["name"] == "needs_edit"
    assert props["AI Grounding Score"]["number"] == 70
    assert props["AI Depth Score"]["number"] == 65
    assert props["AI Financial Safety Score"]["number"] == 90


def test_article_quality_report_properties_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    bundle["article_quality_report"] = {
        "editor_ready_score": 82,
        "final_recommended_status": "needs_review",
    }
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Editor Ready Score"]["number"] == 82
    assert props["Final Recommended Status"]["select"]["name"] == "needs_review"


def test_prompt_version_and_model_are_mapped():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target
    )

    assert props["Prompt Version"]["rich_text"][0]["text"]["content"] == "article_draft@unit+id"
    assert props["LLM Model"]["rich_text"][0]["text"]["content"] == "unit-model"


def test_properties_include_content_job_key():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target,
        content_job_key="job-key",
    )

    assert props["Content Job Key"]["rich_text"][0]["text"]["content"] == "job-key"


def test_properties_include_source_bundle_hash():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target,
        source_bundle_hash="bundle-hash",
    )

    assert props["Source Bundle Hash"]["rich_text"][0]["text"]["content"] == "bundle-hash"


def test_properties_include_pipeline_run_id_from_argument():
    article, market, profile, bundle, validation, llm, target = _context()
    props = NotionPropertyMapper().build_properties(
        article=article, market=market, language_profile=profile, source_bundle=bundle, validation=validation, llm=llm, target=target,
        pipeline_run_id="run-id",
    )

    assert props["Pipeline Run ID"]["rich_text"][0]["text"]["content"] == "run-id"


def test_blocks_include_article_body():
    article, _, _, bundle, validation, llm, _ = _context()
    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Article Body" in _block_text(block) for block in blocks)
    assert any("Pembuka." in _block_text(block) for block in blocks)


def test_blocks_include_editorial_brief_and_notes():
    article, _, _, bundle, validation, llm, _ = _context()
    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Editorial Brief" in _block_text(block) for block in blocks)
    assert any(article["editorial_angle"] in _block_text(block) for block in blocks)
    assert any("Editor Notes" in _block_text(block) for block in blocks)
    assert any("readability" in _block_text(block) for block in blocks)


def test_blocks_include_structured_editorial_brief_when_available():
    article, _, _, bundle, validation, llm, _ = _context()
    bundle["editorial_brief"] = {
        "content_type": "market_brief",
        "confidence_level": "low",
        "primary_angle": "Summarize known facts and source limits.",
        "event_summary": "USD/IDR source event.",
        "why_it_matters": "Readers need context.",
        "market_context": "FX context.",
        "target_reader": "Retail FX readers",
        "reader_questions": ["What happened?"],
        "must_cover": ["Source limitations"],
        "avoid_claims": ["No trading advice"],
        "source_gaps": ["not_enough_usable_sources_for_deep_article"],
        "recommended_structure": ["Ikhtisar singkat"],
    }
    bundle["brief_validation"] = {
        "passed": True,
        "recommended_status": "write_brief_only",
        "issues": [{"severity": "warning", "code": "low_confidence", "message": "Brief confidence is low."}],
    }

    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Content type: market_brief" in _block_text(block) for block in blocks)
    assert any("Primary angle: Summarize known facts" in _block_text(block) for block in blocks)
    assert any("Source gap: not_enough_usable_sources_for_deep_article" in _block_text(block) for block in blocks)
    assert any("Brief validation: write_brief_only" in _block_text(block) for block in blocks)


def test_blocks_include_ai_review_when_available():
    article, _, _, bundle, validation, llm, _ = _context()
    bundle["ai_review"] = {
        "publish_readiness": "needs_edit",
        "reviewer_mode": "deterministic",
        "recommended_editor_action": "Send to editor with highlighted issues or rewrite before review.",
        "scores": {
            "grounding": 70,
            "depth": 65,
            "readability": 80,
            "headline_quality": 85,
            "financial_safety": 90,
            "source_usefulness": 75,
        },
        "unsupported_claims": ["Unknown source URL"],
        "overstatements": [],
        "missing_context": ["Missing source gaps."],
        "issues": [{"severity": "medium", "issue_type": "unsupported_claim", "description": "Unknown source URL"}],
    }

    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Readiness: needs_edit" in _block_text(block) for block in blocks)
    assert any("grounding=70" in _block_text(block) for block in blocks)
    assert any("Unsupported claim: Unknown source URL" in _block_text(block) for block in blocks)
    assert any("Issue: medium - unsupported_claim" in _block_text(block) for block in blocks)


def test_blocks_include_article_quality_report_when_available():
    article, _, _, bundle, validation, llm, _ = _context()
    bundle["article_quality_report"] = {
        "final_recommended_status": "needs_edit",
        "editor_ready_score": 68,
        "source_count": 2,
        "usable_source_count": 1,
        "body_length": 900,
        "faq_count": 1,
        "has_market_context": True,
        "has_risk_disclaimer": True,
        "has_source_attribution": True,
        "headline_risk_level": "medium",
        "financial_advice_detected": False,
        "grounded_claim_ratio": 0.8,
        "blocking_issues": [],
        "warnings": ["source_quality: write_brief_only"],
    }

    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Final status: needs_edit" in _block_text(block) for block in blocks)
    assert any("Editor ready score: 68" in _block_text(block) for block in blocks)
    assert any("Warning: source_quality: write_brief_only" in _block_text(block) for block in blocks)


def test_blocks_include_rewrite_plan_when_available():
    article, _, _, bundle, validation, llm, _ = _context()
    bundle["rewrite_plan"] = {
        "enabled": True,
        "status": "suggested",
        "should_rewrite": True,
        "automatic_rewrite_performed": False,
        "reason": "Rewrite is suggested, but automatic rewriting is not enabled in this phase.",
        "actions": [
            {
                "action_type": "remove_or_source_claim",
                "priority": "high",
                "suggested_change": "Remove unsupported macro claim.",
            }
        ],
        "warnings": ["missing_article"],
    }

    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Rewrite Plan" in _block_text(block) for block in blocks)
    assert any("Status: suggested" in _block_text(block) for block in blocks)
    assert any("Automatic rewrite performed: False" in _block_text(block) for block in blocks)
    assert any("Action: high - remove_or_source_claim" in _block_text(block) for block in blocks)
    assert any("Rewrite warning: missing_article" in _block_text(block) for block in blocks)


def test_long_body_is_chunked():
    long_body = "Sumber\nhttps://example.com/a\n\n" + ("x" * 4000) + "\n\nCatatan risiko\nRisiko."
    article, _, _, bundle, validation, llm, _ = _context(body=long_body)

    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert sum(1 for block in blocks if block["type"] == "paragraph") > 4


def test_blocks_include_sources():
    article, _, _, bundle, validation, llm, _ = _context()
    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Sources" in _block_text(block) for block in blocks)
    assert any("https://example.com/a" in _block_text(block) for block in blocks)


def test_blocks_include_validation_results():
    article, _, _, bundle, validation, llm, _ = _context()
    blocks = NotionBlockBuilder().build_blocks(article=article, source_bundle=bundle, validation=validation, llm=llm)

    assert any("Validation Results" in _block_text(block) for block in blocks)
    assert any("article_schema" in _block_text(block) for block in blocks)


def _block_text(block):
    block_type = block["type"]
    rich_text = block[block_type].get("rich_text") or []
    return " ".join(item.get("text", {}).get("content", "") for item in rich_text)
