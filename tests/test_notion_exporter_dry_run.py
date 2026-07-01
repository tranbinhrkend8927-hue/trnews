from src.config.loader import load_config_registry
from src.notion.exporter import NotionDryRunExporter
from src.notion.target_resolver import ResolvedNotionTarget
from tests.test_article_schema import valid_article


class FakeResolver:
    def __init__(self, target):
        self.target = target

    def resolve(self, target_name):
        return self.target


def _inputs():
    registry = load_config_registry()
    profile = registry.languages["id"]
    article = valid_article(
        risk_disclaimer=profile.risk_disclaimer,
        body="Sumber\nhttps://example.com/a\n\nCatatan risiko\n" + profile.risk_disclaimer,
    )
    return {
        "target_name": "notion_articles_id",
        "article": article,
        "market": registry.pipeline.markets[0],
        "language_profile": profile,
        "source_bundle": {"source_trace": {}, "source_bundle_hash": "hash"},
        "validation": {"article_schema": {"passed": True, "issues": []}},
        "llm": {"prompt_version": "unit", "model": "unit-model"},
    }


def test_build_payload_success():
    target = ResolvedNotionTarget(name="notion_articles_id", language="id", market="Indonesia", parent_type="data_source", parent_id="ds")

    result = NotionDryRunExporter(FakeResolver(target)).build_payload(**_inputs())

    assert result.success is True
    assert result.dry_run is True


def test_payload_contains_target_parent_properties_blocks():
    target = ResolvedNotionTarget(name="notion_articles_id", language="id", market="Indonesia", parent_type="data_source", parent_id="ds")

    payload = NotionDryRunExporter(FakeResolver(target)).build_payload(**_inputs()).payload

    assert payload.target["name"] == "notion_articles_id"
    assert payload.parent == {"data_source_id": "ds"}
    assert payload.properties
    assert payload.blocks


def test_missing_parent_id_warns_but_succeeds():
    target = ResolvedNotionTarget(
        name="notion_articles_id",
        language="id",
        market="Indonesia",
        parent_type="data_source",
        parent_id=None,
        warnings=[{"type": "missing_notion_parent_id"}],
    )

    result = NotionDryRunExporter(FakeResolver(target)).build_payload(**_inputs())

    assert result.success is True
    assert any(warning["type"] == "missing_notion_parent_id" for warning in result.payload.warnings)


def test_does_not_call_notion_api():
    target = ResolvedNotionTarget(name="notion_articles_id", language="id", market="Indonesia", parent_type="data_source", parent_id="ds")

    result = NotionDryRunExporter(FakeResolver(target)).build_payload(**_inputs())

    assert result.page_id is None
    assert result.url is None
