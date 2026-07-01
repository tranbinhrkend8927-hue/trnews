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
