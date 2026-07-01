from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import (
    ConfigError,
    ConfigRegistry,
    LanguageConfig,
    LLMProfilesConfig,
    NotionTargetsConfig,
    PipelineConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_local_env(root: Path | None = None) -> dict[str, str]:
    project_root = root or PROJECT_ROOT
    file_values = _load_dotenv(project_root / ".env")
    return {**file_values, **os.environ}


def _parse_structured_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        yaml = None

    try:
        if yaml is not None:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except Exception as exc:  # pragma: no cover - exact parser exception varies.
        raise ConfigError(f"Unable to parse {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping")
    return data


def load_config_registry(config_dir: str | Path | None = None) -> ConfigRegistry:
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    if not root.exists():
        raise ConfigError(f"Config directory does not exist: {root}")

    pipeline = PipelineConfig.from_mapping(_parse_structured_file(root / "pipeline.yaml"))
    llm_profiles = LLMProfilesConfig.from_mapping(_parse_structured_file(root / "llm_profiles.yaml"))
    notion_targets = NotionTargetsConfig.from_mapping(_parse_structured_file(root / "notion_targets.yaml"))

    language_dir = root / "languages"
    languages: dict[str, LanguageConfig] = {}
    if language_dir.exists():
        for path in sorted(language_dir.glob("*.yaml")):
            language_config = LanguageConfig.from_mapping(_parse_structured_file(path))
            languages[language_config.language] = language_config

    return ConfigRegistry(
        root=root,
        pipeline=pipeline,
        llm_profiles=llm_profiles,
        notion_targets=notion_targets,
        languages=languages,
    )
