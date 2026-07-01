import pytest

from src.config import loader
from src.config.loader import load_config_registry
from src.notion.target_resolver import NotionTargetResolver, ResolvedNotionTarget, build_notion_parent_payload


def use_empty_local_env(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, "PROJECT_ROOT", tmp_path)


def test_target_resolves():
    target = NotionTargetResolver(load_config_registry()).resolve("notion_articles_id")

    assert target.name == "notion_articles_id"
    assert target.language == "id"
    assert target.parent_type == "data_source"


def test_primary_env_is_used(monkeypatch):
    monkeypatch.setenv("NOTION_DATA_SOURCE_ID_ID", "primary-id")
    monkeypatch.setenv("NOTION_DATA_SOURCE_ID", "fallback-id")

    target = NotionTargetResolver(load_config_registry()).resolve("notion_articles_id")

    assert target.parent_id == "primary-id"
    assert target.resolved_from_env == "NOTION_DATA_SOURCE_ID_ID"
    assert target.warnings == []


def test_fallback_env_is_used_with_warning(monkeypatch, tmp_path):
    use_empty_local_env(monkeypatch, tmp_path)
    monkeypatch.delenv("NOTION_DATA_SOURCE_ID_ID", raising=False)
    monkeypatch.setenv("NOTION_DATA_SOURCE_ID", "fallback-id")

    target = NotionTargetResolver(load_config_registry()).resolve("notion_articles_id")

    assert target.parent_id == "fallback-id"
    assert target.resolved_from_env == "NOTION_DATA_SOURCE_ID"
    assert any(warning["type"] == "notion_parent_fallback_env" for warning in target.warnings)


def test_missing_env_returns_none_with_warning(monkeypatch, tmp_path):
    use_empty_local_env(monkeypatch, tmp_path)
    monkeypatch.delenv("NOTION_DATA_SOURCE_ID_ID", raising=False)
    monkeypatch.delenv("NOTION_DATA_SOURCE_ID", raising=False)

    target = NotionTargetResolver(load_config_registry()).resolve("notion_articles_id")

    assert target.parent_id is None
    assert any(warning["type"] == "missing_notion_parent_id" for warning in target.warnings)


def test_unknown_target_raises():
    with pytest.raises(ValueError):
        NotionTargetResolver(load_config_registry()).resolve("missing")


def test_data_source_parent_payload_uses_data_source_id():
    target = ResolvedNotionTarget(name="t", language="id", market="Indonesia", parent_type="data_source", parent_id="ds")

    assert build_notion_parent_payload(target) == {"data_source_id": "ds"}


def test_database_parent_payload_uses_database_id():
    target = ResolvedNotionTarget(name="t", language="id", market="Indonesia", parent_type="database", parent_id="db")

    assert build_notion_parent_payload(target) == {"database_id": "db"}


def test_page_parent_payload_uses_page_id():
    target = ResolvedNotionTarget(name="t", language="id", market="Indonesia", parent_type="page", parent_id="page")

    assert build_notion_parent_payload(target) == {"page_id": "page"}
