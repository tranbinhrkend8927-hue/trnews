from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config.loader import DEFAULT_CONFIG_DIR, load_config_registry
from src.config.models import ConfigError
from src.config.validator import validate_config_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline configuration.")
    parser.add_argument(
        "--config-dir",
        default=str(DEFAULT_CONFIG_DIR),
        help="Directory containing pipeline.yaml, llm_profiles.yaml, notion_targets.yaml, and languages/.",
    )
    args = parser.parse_args(argv)

    try:
        registry = load_config_registry(Path(args.config_dir))
        result = validate_config_registry(registry)
    except ConfigError as exc:
        result_payload = {"success": False, "errors": [str(exc)], "warnings": []}
        print(json.dumps(result_payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
