import importlib
import os
import sys

import pytest


_LEGACY_MODULE_ALIASES = {
    "article_drafts": "news_pipeline.article_drafts",
    "article_review": "news_pipeline.article_review",
    "article_templates": "news_pipeline.article_templates",
    "compare_article_drafts": "news_pipeline.compare_article_drafts",
    "content_topics": "news_pipeline.content_topics",
    "draft_comparison": "news_pipeline.draft_comparison",
    "draft_quality": "news_pipeline.draft_quality",
    "export_article_to_notion": "news_pipeline.export_article_to_notion",
    "fetch_forex_news_json": "news_pipeline.fetch_forex_news_json",
    "generate_article_drafts": "news_pipeline.generate_article_drafts",
    "generate_content_topics": "news_pipeline.generate_content_topics",
    "generate_llm_article_draft": "news_pipeline.generate_llm_article_draft",
    "language_profiles": "news_pipeline.language_profiles",
    "llm_article_drafts": "news_pipeline.llm_article_drafts",
    "llm_article_prompts": "news_pipeline.llm_article_prompts",
    "llm_config": "news_pipeline.llm_config",
    "llm_gateway": "news_pipeline.llm_gateway",
    "llm_providers": "news_pipeline.llm_providers",
    "llm_providers.openrouter": "news_pipeline.llm_providers.openrouter",
    "llm_schemas": "news_pipeline.llm_schemas",
    "notion_config": "news_pipeline.notion_config",
    "notion_exporter": "news_pipeline.notion_exporter",
    "review_article": "news_pipeline.review_article",
    "safety_validation": "news_pipeline.safety_validation",
    "save_selected_article_draft": "news_pipeline.save_selected_article_draft",
    "selected_article_draft": "news_pipeline.selected_article_draft",
    "smoke_article_pipeline": "news_pipeline.smoke_article_pipeline",
    "source_grounding": "news_pipeline.source_grounding",
}


for legacy_name, module_path in _LEGACY_MODULE_ALIASES.items():
    sys.modules.setdefault(legacy_name, importlib.import_module(module_path))


def pytest_collection_modifyitems(config, items):
    skip_live_network = pytest.mark.skip(
        reason="set RUN_LIVE_NETWORK=1 to run live network tests"
    )
    skip_live_llm = pytest.mark.skip(
        reason="set RUN_LLM_LIVE=1 to run live LLM tests"
    )
    skip_live_notion = pytest.mark.skip(
        reason="set RUN_NOTION_LIVE=1 to run live Notion tests"
    )
    for item in items:
        if "live_network" in item.keywords and os.getenv("RUN_LIVE_NETWORK") != "1":
            item.add_marker(skip_live_network)
        if "live_llm" in item.keywords and os.getenv("RUN_LLM_LIVE") != "1":
            item.add_marker(skip_live_llm)
        if "live_notion" in item.keywords and os.getenv("RUN_NOTION_LIVE") != "1":
            item.add_marker(skip_live_notion)
