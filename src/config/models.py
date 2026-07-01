from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


class ConfigError(ValueError):
    """Raised when configuration files cannot be loaded or parsed."""


@dataclass(frozen=True)
class SourcePolicy:
    min_sources: int = 1
    max_sources: int = 5
    require_body: bool = True
    allow_paywalled_summary: bool = True
    max_source_age_hours: int | None = 72

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "SourcePolicy":
        return cls(**(data or {}))


@dataclass(frozen=True)
class TradingViewSourceConfig:
    language: str
    url: str
    locale: str | None = None
    sort: str = "latest"
    section: str = "all"
    provider: str | None = None
    area: str | None = None
    max_headlines: int = 10
    max_articles: int = 3

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "TradingViewSourceConfig":
        return cls(**data)


@dataclass(frozen=True)
class ContentConfig:
    language: str
    market: str
    task: str = "article_draft"
    article_type: str = "fx_news_explainer"
    topic_strategy: str = "latest_forex_news"
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ContentConfig":
        values = dict(data)
        values["source_policy"] = SourcePolicy.from_mapping(values.get("source_policy"))
        return cls(**values)


@dataclass(frozen=True)
class LLMBindingConfig:
    draft_profile: str
    review_profile: str | None = None
    grounding_profile: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LLMBindingConfig":
        return cls(**data)


@dataclass(frozen=True)
class NotionBindingConfig:
    target: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NotionBindingConfig":
        return cls(**data)


@dataclass(frozen=True)
class MarketPipelineConfig:
    id: str
    symbol: str
    exchange: str
    base_currency: str
    quote_currency: str
    tradingview: TradingViewSourceConfig
    content: ContentConfig
    llm: LLMBindingConfig
    notion: NotionBindingConfig
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "MarketPipelineConfig":
        values = dict(data)
        values["tradingview"] = TradingViewSourceConfig.from_mapping(values["tradingview"])
        values["content"] = ContentConfig.from_mapping(values["content"])
        values["llm"] = LLMBindingConfig.from_mapping(values["llm"])
        values["notion"] = NotionBindingConfig.from_mapping(values["notion"])
        return cls(**values)


@dataclass(frozen=True)
class PipelineConfig:
    version: int
    defaults: dict[str, Any]
    markets: list[MarketPipelineConfig]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "PipelineConfig":
        markets = [MarketPipelineConfig.from_mapping(item) for item in data.get("markets", [])]
        return cls(version=data["version"], defaults=data.get("defaults", {}), markets=markets)


@dataclass(frozen=True)
class LLMProviderConfig:
    base_url_env: str | None = None
    base_url_default: str | None = None
    api_key_env: str | None = None
    api_key_fallback_env: str | None = None
    api_key_fallback_value: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LLMProviderConfig":
        return cls(**data)


@dataclass(frozen=True)
class LLMProfileConfig:
    provider: str
    model_env: str | None = None
    fallback_model_env: str | None = None
    fallback_model_value: str | None = None
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 1000
    timeout_seconds: int = 60
    max_retries: int = 1
    response_format: str = "json_schema"
    supports_json_schema: bool = True
    supports_tools: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LLMProfileConfig":
        return cls(**data)


@dataclass(frozen=True)
class LLMProfilesConfig:
    providers: dict[str, LLMProviderConfig]
    profiles: dict[str, LLMProfileConfig]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LLMProfilesConfig":
        providers = {
            key: LLMProviderConfig.from_mapping(value)
            for key, value in data.get("providers", {}).items()
        }
        profiles = {
            key: LLMProfileConfig.from_mapping(value)
            for key, value in data.get("profiles", {}).items()
        }
        return cls(providers=providers, profiles=profiles)


@dataclass(frozen=True)
class NotionTargetConfig:
    language: str
    market: str
    parent_type: Literal["data_source", "database", "page"] = "data_source"
    data_source_id_env: str | None = None
    fallback_data_source_id_env: str | None = None
    fallback_data_source_id_value: str | None = None
    database_id_env: str | None = None
    fallback_database_id_env: str | None = None
    fallback_database_id_value: str | None = None
    page_id_env: str | None = None
    fallback_page_id_env: str | None = None
    fallback_page_id_value: str | None = None
    status_default: str = "AI Draft"
    reviewer_status: str = "Needs Review"
    duplicate_policy: str = "update_existing"
    unique_key_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NotionTargetConfig":
        return cls(**data)


@dataclass(frozen=True)
class NotionTargetsConfig:
    targets: dict[str, NotionTargetConfig]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NotionTargetsConfig":
        targets = {
            key: NotionTargetConfig.from_mapping(value)
            for key, value in data.get("targets", {}).items()
        }
        return cls(targets=targets)


@dataclass(frozen=True)
class LanguageConfig:
    language: str
    locale: str
    market: str
    audience: str
    tone: str
    writing_rules: list[str]
    required_sections: list[str]
    risk_disclaimer: str
    forbidden_claims: list[str]
    seo: dict[str, Any]
    slug: dict[str, Any]
    notion: dict[str, Any]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LanguageConfig":
        return cls(**data)


@dataclass(frozen=True)
class ConfigRegistry:
    root: Path
    pipeline: PipelineConfig
    llm_profiles: LLMProfilesConfig
    notion_targets: NotionTargetsConfig
    languages: dict[str, LanguageConfig]

    def enabled_markets(self) -> list[MarketPipelineConfig]:
        return [market for market in self.pipeline.markets if market.enabled]


@dataclass(frozen=True)
class ConfigValidationResult:
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
        }
