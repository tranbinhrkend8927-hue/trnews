import importlib

from news_pipeline import article_drafts as packaged_article_drafts
from news_pipeline.llm_providers import openrouter as packaged_openrouter


def test_legacy_top_level_module_aliases_resolve_to_news_pipeline_modules():
    legacy_module = importlib.import_module("article_drafts")

    assert legacy_module is packaged_article_drafts


def test_legacy_package_aliases_resolve_nested_modules():
    legacy_module = importlib.import_module("llm_providers.openrouter")

    assert legacy_module is packaged_openrouter
