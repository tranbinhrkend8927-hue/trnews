from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from src.config.loader import load_config_registry, load_local_env
from src.config.models import ConfigError
from src.content.article_pipeline import build_article_brief_for_llm
from src.llm.prompt_renderer import PromptRenderer
from src.notion.exporter import NotionDryRunExporter
from src.notion.target_resolver import NotionTargetResolver


def production_check_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check readiness for a safe first real content run.")
    parser.add_argument("--market")
    parser.add_argument("--enabled-only", action="store_true")
    parser.add_argument("--require-real-llm", action="store_true")
    parser.add_argument("--require-notion", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON. JSON is the default format.")
    namespace = parser.parse_args(args)

    try:
        registry = load_config_registry()
        markets = _select_markets(registry, market_id=namespace.market, enabled_only=namespace.enabled_only)
    except (ConfigError, ValueError) as exc:
        print(json.dumps({"success": False, "status": "PRODUCTION_CHECK_ARGUMENT_ERROR", "errors": [{"message": str(exc)}]}, ensure_ascii=False, indent=2))
        return 2

    payload = _run_checks(
        registry,
        markets,
        require_real_llm=namespace.require_real_llm,
        require_notion=namespace.require_notion,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["success"] else 1


def _select_markets(registry, *, market_id: str | None, enabled_only: bool) -> list:
    if market_id:
        for market in registry.pipeline.markets:
            if market.id == market_id:
                return [market]
        raise ValueError(f"Unknown market id: {market_id}")
    if enabled_only:
        return registry.enabled_markets()
    return registry.enabled_markets()


def _run_checks(registry, markets: list, *, require_real_llm: bool, require_notion: bool) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    checks = {
        "config": {"success": True, "markets": []},
        "environment": {"success": True, "items": []},
        "prompt": {"success": True, "items": []},
        "notion_payload": {"success": True, "items": []},
        "safety": {
            "success": True,
            "default_no_real_llm": True,
            "default_no_notion_write": True,
            "notion_write_requires_explicit_flag": True,
            "real_llm_requires_explicit_flag": True,
        },
    }
    env = load_local_env()
    for market in markets:
        _check_config_market(registry, market, checks, errors)
        _check_environment(registry, market, env, checks, errors, warnings, require_real_llm=require_real_llm, require_notion=require_notion)
        _check_prompt(registry, market, checks, errors)
        _check_notion_payload(registry, market, checks, errors, warnings)

    success = not errors
    return {
        "success": success,
        "status": "PRODUCTION_CHECK_PASSED" if success else "PRODUCTION_CHECK_FAILED",
        "checked_markets": [market.id for market in markets],
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def _check_config_market(registry, market, checks: dict, errors: list[dict]) -> None:
    item = {"market_id": market.id, "success": True}
    if market.content.language not in registry.languages:
        _fail(item, checks["config"], errors, "missing_language_profile", market_id=market.id)
    if market.llm.draft_profile not in registry.llm_profiles.profiles:
        _fail(item, checks["config"], errors, "missing_llm_profile", market_id=market.id)
    if market.notion.target not in registry.notion_targets.targets:
        _fail(item, checks["config"], errors, "missing_notion_target", market_id=market.id)
    if not market.tradingview.url:
        _fail(item, checks["config"], errors, "missing_tradingview_url", market_id=market.id)
    policy = market.content.source_policy
    if policy.min_sources < 1 or policy.max_sources < policy.min_sources:
        _fail(item, checks["config"], errors, "invalid_source_policy", market_id=market.id)
    checks["config"]["markets"].append(item)


def _check_environment(registry, market, env: dict, checks: dict, errors: list[dict], warnings: list[dict], *, require_real_llm: bool, require_notion: bool) -> None:
    profile = registry.llm_profiles.profiles.get(market.llm.draft_profile)
    provider = registry.llm_profiles.providers.get(profile.provider) if profile else None
    required_or_warning = [
        ("LLM_API_KEY", provider.api_key_env if provider else None, require_real_llm),
        ("LLM_BASE_URL", provider.base_url_env if provider else None, require_real_llm),
        ("LLM_MODEL", profile.model_env if profile else None, require_real_llm),
    ]
    for label, env_name, required in required_or_warning:
        _env_check(label, env_name, env, checks, errors, warnings, required=required, market_id=market.id)
    target = registry.notion_targets.targets.get(market.notion.target)
    _env_check("NOTION_API_KEY", "NOTION_API_KEY", env, checks, errors, warnings, required=require_notion, market_id=market.id)
    for env_name in _target_parent_env_names(target):
        _env_check("NOTION_PARENT_ID", env_name, env, checks, errors, warnings, required=require_notion, market_id=market.id)
        break


def _check_prompt(registry, market, checks: dict, errors: list[dict]) -> None:
    item = {"market_id": market.id, "success": True}
    try:
        PromptRenderer().render(
            market.content.task,
            market.content.language,
            _fake_prompt_input(registry, market),
        )
    except Exception as exc:
        _fail(item, checks["prompt"], errors, "prompt_render_failed", market_id=market.id, message=str(exc))
    checks["prompt"]["items"].append(item)


def _check_notion_payload(registry, market, checks: dict, errors: list[dict], warnings: list[dict]) -> None:
    item = {"market_id": market.id, "success": True}
    try:
        result = NotionDryRunExporter(NotionTargetResolver(registry)).build_payload(
            target_name=market.notion.target,
            article=_fake_article(market),
            market=market,
            language_profile=asdict(registry.languages[market.content.language]),
            source_bundle=_fake_source_bundle(market),
            validation={"article_schema": {"passed": True, "issues": []}},
            llm={"model": "dry-run", "prompt_version": "dry-run"},
            pipeline_run_id="run-production-check",
            content_job_key="production-check-job-key",
            source_bundle_hash="production-check-source-hash",
        )
        payload = result.payload
        properties = payload.properties if payload else {}
        required_props = ["Name", "Status", "Language", "Market", "Symbol", "Content Job Key", "Source Bundle Hash", "Pipeline Run ID"]
        missing = [name for name in required_props if name not in properties]
        parent = payload.parent if payload else {}
        item.update({"parent_keys": list(parent.keys()), "block_count": len(payload.blocks if payload else [])})
        if missing:
            _fail(item, checks["notion_payload"], errors, "missing_notion_properties", market_id=market.id, properties=missing)
        if payload and not payload.blocks:
            _fail(item, checks["notion_payload"], errors, "empty_notion_blocks", market_id=market.id)
        for warning in (payload.warnings if payload else []):
            warnings.append({"market_id": market.id, **warning})
    except Exception as exc:
        _fail(item, checks["notion_payload"], errors, "notion_payload_failed", market_id=market.id, message=str(exc))
    checks["notion_payload"]["items"].append(item)


def _env_check(label: str, env_name: str | None, env: dict, checks: dict, errors: list[dict], warnings: list[dict], *, required: bool, market_id: str) -> None:
    if not env_name:
        return
    ok = bool(env.get(env_name) or os.getenv(env_name))
    item = {"market_id": market_id, "label": label, "env": env_name, "present": ok, "required": required}
    checks["environment"]["items"].append(item)
    if ok:
        return
    issue = {"type": "missing_env", "market_id": market_id, "env": env_name, "required": required}
    if required:
        errors.append(issue)
        checks["environment"]["success"] = False
    else:
        warnings.append(issue)


def _target_parent_env_names(target) -> list[str]:
    if target is None:
        return []
    if target.parent_type == "data_source":
        return [name for name in [target.data_source_id_env, target.fallback_data_source_id_env] if name]
    if target.parent_type == "database":
        return [name for name in [target.database_id_env, target.fallback_database_id_env] if name]
    if target.parent_type == "page":
        return [name for name in [target.page_id_env, target.fallback_page_id_env] if name]
    return []


def _fail(item: dict, section: dict, errors: list[dict], error_type: str, **details) -> None:
    item["success"] = False
    section["success"] = False
    errors.append({"type": error_type, **details})


def _fake_source_bundle(market) -> dict:
    return {
        "bundle_id": "production-check",
        "market_id": market.id,
        "symbol": market.symbol,
        "language": market.content.language,
        "source_bundle_hash": "production-check-source-hash",
        "sources": [
            {
                "source_id": "source-1",
                "title": f"{market.symbol} production check source",
                "url": "https://example.com/source",
                "provider": "Example",
                "published_at": "2026-07-01T00:00:00Z",
                "summary": "Production check source summary.",
                "content": "Production check source body.",
            }
        ],
        "source_trace": {"source_count": 1, "source_ids": ["source-1"]},
    }


def _fake_prompt_input(registry, market) -> dict:
    language_profile = asdict(registry.languages[market.content.language])
    source_bundle = _fake_source_bundle(market)
    return {
        "article_brief": build_article_brief_for_llm(
            market=market,
            language_profile=language_profile,
            source_bundle=source_bundle,
        ),
        "market": asdict(market),
        "language_profile": language_profile,
        "source_bundle": source_bundle,
    }


def _fake_article(market) -> dict:
    return {
        "title": f"{market.symbol}: production check",
        "slug": f"{market.symbol.lower()}-production-check",
        "summary": "Production readiness check article summary.",
        "body": "Production readiness check body.\n\nSumber\nExample source\n\nCatatan risiko\nInformasi ini hanya untuk edukasi.",
        "seo_title": f"{market.symbol}: production check",
        "seo_description": "Production readiness check article summary.",
        "language": market.content.language,
        "market": market.content.market,
        "symbol": market.symbol,
        "article_type": market.content.article_type,
        "risk_disclaimer": "Informasi ini hanya untuk edukasi dan bukan rekomendasi investasi.",
        "faq": [],
        "sources_used": [{"source_id": "source-1", "title": "Example source", "url": "https://example.com/source", "provider": "Example", "used_for": "production_check"}],
        "uncertain_claims": [],
    }


def main() -> int:
    return production_check_command()


if __name__ == "__main__":
    sys.exit(main())
