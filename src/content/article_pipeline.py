from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from src.content.article_schema import ArticleDraft
from src.content.source_bundle import SourceBundleBuilder, source_bundle_to_dict
from src.content.validators._utils import article_to_dict
from src.content.validators.article_schema import validate_article_schema
from src.content.validators.financial_safety import validate_financial_safety
from src.content.validators.language_rules import validate_language_rules
from src.content.validators.notion_exportable import validate_notion_exportable
from src.content.validators.source_grounding import validate_source_grounding
from src.jobs.idempotency import compute_content_job_key, compute_daily_content_job_key, compute_pipeline_run_id, compute_source_bundle_hash
from src.llm.result import LLMTaskResult


LLM_SOURCE_CONTENT_CHAR_LIMIT = 300


class ArticlePipeline:
    def __init__(
        self,
        config_registry,
        tradingview_adapter,
        source_bundle_builder,
        llm_runner=None,
        notion_exporter=None,
        append_update_note: bool = False,
        content_job_key_mode: str = "daily",
    ):
        self.config_registry = config_registry
        self.tradingview_adapter = tradingview_adapter
        self.source_bundle_builder = source_bundle_builder
        self.llm_runner = llm_runner
        self.notion_exporter = notion_exporter
        self.append_update_note = append_update_note
        self.content_job_key_mode = content_job_key_mode

    def run_market(self, market_id: str, *, dry_run: bool = True) -> dict:
        market = self._market_by_id(market_id)
        if market is None:
            return {
                "success": False,
                "status": "MARKET_NOT_FOUND",
                "market_id": market_id,
                "errors": [{"type": "market_not_found", "market_id": market_id}],
            }

        language_profile_model = self.config_registry.languages.get(market.content.language)
        language_profile = _model_to_dict(language_profile_model) if language_profile_model is not None else {}
        fetch_result = self.tradingview_adapter.fetch(market)
        source_bundle = self.source_bundle_builder.build(market, fetch_result)
        source_bundle_dict = source_bundle_to_dict(source_bundle)
        source_bundle_hash = compute_source_bundle_hash(source_bundle_dict)
        source_bundle_dict["source_bundle_hash"] = source_bundle_hash
        pipeline_run_id = compute_pipeline_run_id(
            market_id=market.id,
            symbol=market.symbol,
            language=market.content.language,
        )
        if self.content_job_key_mode == "source_hash":
            content_job_key = compute_content_job_key(
                market_id=market.id,
                symbol=market.symbol,
                language=market.content.language,
                task=market.content.task,
                source_bundle_hash=source_bundle_hash,
            )
        else:
            content_job_key = compute_daily_content_job_key(
                market_id=market.id,
                symbol=market.symbol,
                language=market.content.language,
                task=market.content.task,
            )

        base_result = {
            "pipeline_run_id": pipeline_run_id,
            "source_bundle_hash": source_bundle_hash,
            "content_job_key": content_job_key,
            "market_id": market.id,
            "symbol": market.symbol,
            "language": market.content.language,
            "task": market.content.task,
            "source_fetch": _model_to_dict(fetch_result),
            "source_bundle": source_bundle_dict,
        }

        if source_bundle.errors:
            return {
                **base_result,
                "success": False,
                "status": "SOURCE_BUNDLE_FAILED",
                "errors": source_bundle.errors,
            }

        llm_result = self._run_llm_or_fake_article(market, language_profile, source_bundle_dict)
        base_result["llm"] = _llm_result_to_dict(llm_result)
        if isinstance(llm_result, LLMTaskResult):
            if not llm_result.success:
                return {
                    **base_result,
                    "success": False,
                    "status": "LLM_FAILED",
                    "errors": [{"type": llm_result.error.type if llm_result.error else "llm_failed"}],
                }
            article_dict = llm_result.output or {}
        else:
            article_dict = article_to_dict(llm_result) if isinstance(llm_result, ArticleDraft) else llm_result

        article_dict = normalize_article_output_for_validation(article_dict)
        validation = self._validate_article(article_dict, source_bundle_dict, language_profile)
        base_result["article"] = article_dict
        base_result["validation"] = validation

        if any(not item["passed"] for item in validation.values()):
            return {
                **base_result,
                "success": False,
                "status": "VALIDATION_FAILED",
            }

        if dry_run and self.notion_exporter is not None:
            notion_result = self.notion_exporter.build_payload(
                target_name=market.notion.target,
                article=article_dict,
                market=market,
                language_profile=language_profile,
                source_bundle=source_bundle_dict,
                validation=validation,
                llm=base_result.get("llm"),
                pipeline_run_id=pipeline_run_id,
                content_job_key=content_job_key,
                source_bundle_hash=source_bundle_hash,
            )
            base_result["notion_preview"] = _model_to_dict(notion_result)

        if not dry_run:
            if self.notion_exporter is None:
                return {
                    **base_result,
                    "success": False,
                    "status": "NOTION_EXPORTER_MISSING",
                    "errors": [{"type": "notion_exporter_missing"}],
                }
            notion_result = self.notion_exporter.export(
                target_name=market.notion.target,
                article=article_dict,
                market=market,
                language_profile=language_profile,
                source_bundle=source_bundle_dict,
                validation=validation,
                llm=base_result.get("llm"),
                pipeline_run_id=pipeline_run_id,
                content_job_key=content_job_key,
                source_bundle_hash=source_bundle_hash,
                append_update_note=self.append_update_note,
            )
            notion_dict = _model_to_dict(notion_result)
            notion_success = notion_result.get("success") if isinstance(notion_result, dict) else notion_result.success
            if notion_success:
                return {
                    **base_result,
                    "success": True,
                    "status": "NOTION_EXPORTED",
                    "notion": notion_dict,
                }
            return {
                **base_result,
                "success": False,
                "status": "NOTION_EXPORT_FAILED",
                "notion": notion_dict,
            }

        return {
            **base_result,
            "success": True,
            "status": "DRY_RUN_SUCCESS",
        }

    def _market_by_id(self, market_id: str):
        for market in self.config_registry.pipeline.markets:
            if market.id == market_id:
                return market
        return None

    def _run_llm_or_fake_article(self, market, language_profile: dict[str, Any], source_bundle: dict[str, Any]):
        if self.llm_runner is not None:
            return self.llm_runner.run(
                task=market.content.task,
                language=market.content.language,
                profile=market.llm.draft_profile,
                input_data={
                    "article_brief": build_article_brief_for_llm(
                        market=market,
                        language_profile=language_profile,
                        source_bundle=source_bundle,
                    ),
                    "market": compact_market_for_llm(market),
                    "language_profile": compact_language_profile_for_llm(language_profile),
                    "source_bundle": compact_source_bundle_for_llm(source_bundle),
                },
            )
        return _fake_article(market, language_profile, source_bundle)

    def _validate_article(self, article: dict[str, Any], source_bundle: dict[str, Any], language_profile: dict[str, Any]) -> dict[str, dict]:
        validators = {
            "article_schema": validate_article_schema(article),
            "source_grounding": validate_source_grounding(article, source_bundle),
            "language_rules": validate_language_rules(article, language_profile),
            "financial_safety": validate_financial_safety(article, language_profile),
            "notion_exportable": validate_notion_exportable(article),
        }
        return {name: _model_to_dict(result) for name, result in validators.items()}


def _fake_article(market, language_profile: dict[str, Any], source_bundle: dict[str, Any]) -> ArticleDraft:
    source = source_bundle["sources"][0]
    disclaimer = language_profile.get("risk_disclaimer") or "Informasi ini hanya untuk edukasi dan bukan rekomendasi investasi."
    required_sections = language_profile.get("required_sections") or ["Sumber", "Catatan risiko"]
    title = f"{market.symbol}: ringkasan berita terbaru"
    seo_description = f"Ringkasan edukatif {market.symbol} berdasarkan sumber berita yang tersedia."
    body = "\n\n".join(
        [
            f"Artikel dry-run ini merangkum konteks {market.symbol} berdasarkan sumber yang tersedia.",
            f"{required_sections[0]}\n{source.get('title')}\n{source.get('url') or source.get('canonical_url') or ''}",
            f"{required_sections[1]}\n{disclaimer}",
        ]
    )
    return ArticleDraft(
        title=title,
        slug=f"{market.symbol.lower()}-dry-run",
        summary=f"Ringkasan dry-run untuk {market.symbol}.",
        body=body,
        seo_title=title[:70],
        seo_description=seo_description[:170],
        language=market.content.language,
        market=market.content.market,
        symbol=market.symbol,
        article_type=market.content.article_type,
        risk_disclaimer=disclaimer,
        faq=[],
        sources_used=[
            {
                "source_id": source["source_id"],
                "news_id": source.get("raw", {}).get("news_id") or source.get("raw", {}).get("id"),
                "title": source["title"],
                "url": source.get("url"),
                "provider": source.get("provider"),
                "published_at": source.get("published_at"),
                "used_for": "dry_run_article_context",
            }
        ],
        uncertain_claims=[],
    )


def _model_to_dict(value):
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if is_dataclass(value):
        return asdict(value)
    return dict(value)


def _llm_result_to_dict(value):
    if isinstance(value, LLMTaskResult):
        return _model_to_dict(value)
    return {
        "success": True,
        "task": "fake_article_draft",
        "output_mode": "fake",
        "metadata": {"reason": "llm_runner_not_configured"},
    }


def normalize_article_output_for_validation(article: Any) -> Any:
    if not isinstance(article, dict):
        return article
    normalized = dict(article)
    sources_used = []
    for source in list(normalized.get("sources_used") or []):
        if not isinstance(source, dict):
            sources_used.append(source)
            continue
        item = dict(source)
        if item.get("source_id") is not None:
            item["source_id"] = str(item.get("source_id"))
        sources_used.append(item)
    normalized["sources_used"] = sources_used
    return normalized


def compact_source_bundle_for_llm(source_bundle: dict[str, Any], *, content_char_limit: int = LLM_SOURCE_CONTENT_CHAR_LIMIT) -> dict[str, Any]:
    """Keep LLM grounding fields while dropping large raw payloads."""
    bundle = dict(source_bundle or {})
    sources = []
    for source in list(bundle.get("sources") or []):
        if not isinstance(source, dict):
            continue
        raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
        compact = {
            "source_id": source.get("source_id"),
            "news_id": source.get("news_id") or raw.get("news_id") or raw.get("id"),
            "provider": source.get("provider") or source.get("source"),
            "symbol": source.get("symbol"),
            "exchange": source.get("exchange"),
            "language": source.get("language"),
            "locale": source.get("locale"),
            "title": source.get("title"),
            "summary": _truncate_text(source.get("summary"), content_char_limit // 2),
            "content": _truncate_text(source.get("content"), content_char_limit),
            "url": source.get("url"),
            "canonical_url": source.get("canonical_url"),
            "published_at": source.get("published_at"),
            "fetched_at": source.get("fetched_at"),
        }
        sources.append({key: value for key, value in compact.items() if value not in (None, "")})

    return {
        "bundle_id": bundle.get("bundle_id"),
        "market_id": bundle.get("market_id"),
        "symbol": bundle.get("symbol"),
        "language": bundle.get("language"),
        "sources": sources,
        "source_bundle_hash": bundle.get("source_bundle_hash"),
        "missing_source_ids": list(bundle.get("missing_source_ids") or []),
        "warnings": list(bundle.get("warnings") or []),
        "errors": list(bundle.get("errors") or []),
        "source_trace": dict(bundle.get("source_trace") or {}),
    }


def build_article_brief_for_llm(*, market: Any, language_profile: dict[str, Any], source_bundle: dict[str, Any]) -> str:
    market_data = compact_market_for_llm(market)
    profile = compact_language_profile_for_llm(language_profile)
    compact_bundle = compact_source_bundle_for_llm(source_bundle)
    disclaimer = profile.get("risk_disclaimer") or ""
    sections = [
        "TASK: Write a short grounded ArticleDraft for this market.",
        f"language: {profile.get('language') or market_data.get('language')}",
        f"market: {market_data.get('market')}",
        f"symbol: {market_data.get('symbol')}",
        f"article_type: {market_data.get('article_type')}",
        f"risk_disclaimer: {disclaimer}",
        "",
        "MERGED_SOURCES:",
    ]

    for index, source in enumerate(compact_bundle.get("sources") or [], start=1):
        title = _single_line(source.get("title"))
        content = _single_line(source.get("content") or source.get("summary"))
        sections.extend(
            [
                f"SOURCE {index}",
                f"source_id: {source.get('source_id')}",
                f"news_id: {source.get('news_id') or source.get('source_id')}",
                f"provider: {source.get('provider')}",
                f"published_at: {source.get('published_at')}",
                f"url: {source.get('canonical_url') or source.get('url')}",
                f"title: {title}",
                f"content: {content}",
                "",
            ]
        )

    sections.extend(
        [
            "REQUIRED_JSON_FIELDS:",
            "title, slug, summary, body, seo_title, seo_description, language, market, symbol, article_type, risk_disclaimer, faq, sources_used, uncertain_claims",
        ]
    )
    return "\n".join(sections).strip()


def compact_market_for_llm(market: Any) -> dict[str, Any]:
    data = _model_to_dict(market)
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    tradingview = data.get("tradingview") if isinstance(data.get("tradingview"), dict) else {}
    return {
        "id": data.get("id"),
        "symbol": data.get("symbol"),
        "exchange": data.get("exchange"),
        "base_currency": data.get("base_currency"),
        "quote_currency": data.get("quote_currency"),
        "market": content.get("market"),
        "language": content.get("language"),
        "task": content.get("task"),
        "article_type": content.get("article_type"),
        "locale": tradingview.get("locale"),
    }


def compact_language_profile_for_llm(language_profile: dict[str, Any]) -> dict[str, Any]:
    profile = dict(language_profile or {})
    return {
        "language": profile.get("language"),
        "locale": profile.get("locale"),
        "tone": profile.get("tone"),
        "required_sections": list(profile.get("required_sections") or []),
        "risk_disclaimer": profile.get("risk_disclaimer"),
        "forbidden_phrases": list(profile.get("forbidden_phrases") or []),
    }


def _truncate_text(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    limit = max(int(limit or 0), 0)
    if limit and len(text) > limit:
        return f"{text[:limit].rstrip()}...[truncated]"
    return text


def _single_line(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split())
