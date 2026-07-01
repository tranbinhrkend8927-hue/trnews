import json
from pathlib import Path

from src.config.loader import load_config_registry
from src.config.validator import validate_config_registry


def test_loads_default_pipeline_and_language_config():
    registry = load_config_registry()

    assert registry.pipeline.version == 1
    assert registry.pipeline.markets[0].id == "usd_idr_id"
    assert registry.languages["id"].market == "Indonesia"
    assert "article_writer_id" in registry.llm_profiles.profiles
    assert "notion_articles_id" in registry.notion_targets.targets


def test_default_registry_validates_with_configured_fallbacks():
    registry = load_config_registry()

    result = validate_config_registry(registry, env={})

    assert result.success is True
    assert result.errors == []
    assert any("LLM_API_KEY" in warning for warning in result.warnings)
    assert any("NOTION_DATA_SOURCE_ID_ID" in warning for warning in result.warnings)


def test_enabled_market_references_existing_language_llm_target_and_prompt():
    registry = load_config_registry()
    result = validate_config_registry(registry, env={})
    market = registry.enabled_markets()[0]

    assert market.content.language in registry.languages
    assert market.llm.draft_profile in registry.llm_profiles.profiles
    assert market.notion.target in registry.notion_targets.targets
    assert Path("src/llm/prompts/article_draft/id.system.md").exists()
    assert result.success is True


def test_language_mismatch_is_an_error(tmp_path):
    _copy_default_config(tmp_path)
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
    pipeline["markets"][0]["tradingview"]["language"] = "ja"
    pipeline_path.write_text(json.dumps(pipeline), encoding="utf-8")

    registry = load_config_registry(tmp_path)
    result = validate_config_registry(registry, env={})

    assert result.success is False
    assert any("language mismatch" in error for error in result.errors)


def test_missing_prompt_file_is_an_error(tmp_path):
    _copy_default_config(tmp_path)
    registry = load_config_registry(tmp_path)

    result = validate_config_registry(registry, env={}, prompt_root=tmp_path / "missing-prompts")

    assert result.success is False
    assert any("prompt file is missing" in error for error in result.errors)


def _copy_default_config(target: Path) -> None:
    source = Path("config")
    for path in source.rglob("*.yaml"):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
