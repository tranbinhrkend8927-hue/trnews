from __future__ import annotations

from pathlib import Path

from .loader import PROJECT_ROOT, load_local_env
from .models import (
    ConfigRegistry,
    ConfigValidationResult,
    LLMProfileConfig,
    LLMProviderConfig,
    NotionTargetConfig,
)


def _resolve_env(
    env: dict[str, str],
    primary_name: str | None,
    fallback_name: str | None = None,
    fallback_value: str | None = None,
) -> tuple[str | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if primary_name and env.get(primary_name):
        return env[primary_name], errors, warnings
    if fallback_name and env.get(fallback_name):
        warnings.append(f"{primary_name} is missing; using fallback env {fallback_name}")
        return env[fallback_name], errors, warnings
    if fallback_value:
        warnings.append(f"{primary_name} is missing; using configured fallback value")
        return fallback_value, errors, warnings
    errors.append(f"{primary_name or 'required env'} is missing and no fallback is configured")
    return None, errors, warnings


def _validate_provider(
    provider_name: str,
    provider: LLMProviderConfig,
    env: dict[str, str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not provider.api_key_env:
        errors.append(f"LLM provider {provider_name} is missing api_key_env")
        return errors, warnings
    _, resolved_errors, resolved_warnings = _resolve_env(
        env,
        provider.api_key_env,
        provider.api_key_fallback_env,
        provider.api_key_fallback_value,
    )
    errors.extend(f"LLM provider {provider_name}: {error}" for error in resolved_errors)
    warnings.extend(f"LLM provider {provider_name}: {warning}" for warning in resolved_warnings)
    return errors, warnings


def _validate_llm_profile(
    profile_name: str,
    profile: LLMProfileConfig,
    registry: ConfigRegistry,
    env: dict[str, str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if profile.provider not in registry.llm_profiles.providers:
        errors.append(f"LLM profile {profile_name} references unknown provider {profile.provider}")
        return errors, warnings
    _, resolved_errors, resolved_warnings = _resolve_env(
        env,
        profile.model_env,
        profile.fallback_model_env,
        profile.fallback_model_value,
    )
    errors.extend(f"LLM profile {profile_name}: {error}" for error in resolved_errors)
    warnings.extend(f"LLM profile {profile_name}: {warning}" for warning in resolved_warnings)
    return errors, warnings


def _validate_notion_target(
    target_name: str,
    target: NotionTargetConfig,
    env: dict[str, str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    parent_fields = {
        "data_source": (
            target.data_source_id_env,
            target.fallback_data_source_id_env,
            target.fallback_data_source_id_value,
            "data_source_id",
        ),
        "database": (
            target.database_id_env,
            target.fallback_database_id_env,
            target.fallback_database_id_value,
            "database_id",
        ),
        "page": (
            target.page_id_env,
            target.fallback_page_id_env,
            target.fallback_page_id_value,
            "page_id",
        ),
    }
    if target.parent_type not in parent_fields:
        errors.append(f"Notion target {target_name} has invalid parent_type {target.parent_type}")
        return errors, warnings

    primary_name, fallback_name, fallback_value, payload_field = parent_fields[target.parent_type]
    _, resolved_errors, resolved_warnings = _resolve_env(env, primary_name, fallback_name, fallback_value)
    errors.extend(f"Notion target {target_name}: {error}" for error in resolved_errors)
    warnings.extend(f"Notion target {target_name}: {warning}" for warning in resolved_warnings)
    if target.parent_type == "data_source" and payload_field != "data_source_id":
        errors.append(f"Notion target {target_name} must use data_source_id payload")
    if target.reviewer_status == "Published" or target.status_default == "Published":
        errors.append(f"Notion target {target_name} must not default to Published")
    return errors, warnings


def validate_config_registry(
    registry: ConfigRegistry,
    *,
    env: dict[str, str] | None = None,
    prompt_root: str | Path | None = None,
) -> ConfigValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    effective_env = env if env is not None else load_local_env(PROJECT_ROOT)
    effective_prompt_root = Path(prompt_root) if prompt_root is not None else PROJECT_ROOT / "src" / "llm" / "prompts"

    market_ids = [market.id for market in registry.pipeline.markets]
    duplicates = sorted({market_id for market_id in market_ids if market_ids.count(market_id) > 1})
    for market_id in duplicates:
        errors.append(f"Duplicate market id: {market_id}")

    used_providers: set[str] = set()
    used_profiles: set[str] = set()
    used_targets: set[str] = set()

    for market in registry.enabled_markets():
        language = market.content.language
        if language not in registry.languages:
            errors.append(f"Market {market.id} references missing language profile {language}")
        if market.tradingview.language != market.content.language:
            errors.append(
                f"Market {market.id} language mismatch: "
                f"tradingview.language={market.tradingview.language}, content.language={market.content.language}"
            )
        if market.content.source_policy.min_sources > market.content.source_policy.max_sources:
            errors.append(f"Market {market.id} has min_sources greater than max_sources")

        prompt_path = effective_prompt_root / market.content.task / f"{language}.system.md"
        if not prompt_path.exists():
            errors.append(f"Market {market.id} prompt file is missing: {prompt_path}")

        profile_names = [
            market.llm.draft_profile,
            market.llm.review_profile,
            market.llm.grounding_profile,
        ]
        for profile_name in [name for name in profile_names if name]:
            used_profiles.add(profile_name)
            profile = registry.llm_profiles.profiles.get(profile_name)
            if profile is None:
                errors.append(f"Market {market.id} references missing LLM profile {profile_name}")
                continue
            used_providers.add(profile.provider)

        used_targets.add(market.notion.target)
        target = registry.notion_targets.targets.get(market.notion.target)
        if target is None:
            errors.append(f"Market {market.id} references missing Notion target {market.notion.target}")
        else:
            if target.language != market.content.language:
                errors.append(f"Market {market.id} references Notion target with different language")
            if target.market != market.content.market:
                errors.append(f"Market {market.id} references Notion target with different market")

    for provider_name in sorted(used_providers):
        provider = registry.llm_profiles.providers.get(provider_name)
        if provider is None:
            errors.append(f"Missing LLM provider {provider_name}")
            continue
        provider_errors, provider_warnings = _validate_provider(provider_name, provider, effective_env)
        errors.extend(provider_errors)
        warnings.extend(provider_warnings)

    for profile_name in sorted(used_profiles):
        profile = registry.llm_profiles.profiles.get(profile_name)
        if profile is None:
            continue
        profile_errors, profile_warnings = _validate_llm_profile(profile_name, profile, registry, effective_env)
        errors.extend(profile_errors)
        warnings.extend(profile_warnings)

    for target_name in sorted(used_targets):
        target = registry.notion_targets.targets.get(target_name)
        if target is None:
            continue
        target_errors, target_warnings = _validate_notion_target(target_name, target, effective_env)
        errors.extend(target_errors)
        warnings.extend(target_warnings)

    return ConfigValidationResult(success=not errors, errors=errors, warnings=warnings)
