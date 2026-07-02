from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any

from src.content.article_schema import ArticleDraft
from src.content.source_bundle import SourceBundleBuilder, source_bundle_to_dict
from src.content.validators._utils import article_to_dict
from src.content.validators.article_schema import validate_article_schema
from src.content.validators.depth_quality import validate_depth_quality
from src.content.validators.financial_safety import validate_financial_safety
from src.content.validators.language_rules import validate_language_rules
from src.content.validators.notion_exportable import validate_notion_exportable
from src.content.validators.source_grounding import validate_source_grounding
from src.ingest.source_enricher import enrich_sources, is_enrichment_enabled
from src.ingest.source_quality import assess_source_quality, is_quality_gate_enabled
from src.jobs.idempotency import compute_content_job_key, compute_daily_content_job_key, compute_pipeline_run_id, compute_source_bundle_hash
from src.llm.result import LLMTaskResult
from src.planning.brief_builder import build_editorial_brief, format_editorial_brief_for_prompt
from src.planning.brief_validator import validate_editorial_brief
from src.review.article_reviewer import is_ai_reviewer_enabled, review_article
from src.review.quality_report import build_article_quality_report


LLM_SOURCE_CONTENT_CHAR_LIMIT = 300
LLM_ENRICHED_SOURCE_CONTENT_CHAR_LIMIT = 1200


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

        # Phase 1: optional source enrichment
        enrichment_results = []
        if is_enrichment_enabled() and fetch_result.items:
            source_dicts = [_model_to_dict(item) for item in fetch_result.items]
            enrichment_results = enrich_sources(source_dicts)

        source_bundle = self.source_bundle_builder.build(market, fetch_result)

        # Attach enrichment results to the bundle
        if enrichment_results:
            enrichment_dicts = [_model_to_dict(r) for r in enrichment_results]
            source_bundle = source_bundle.model_copy(update={"enriched_sources": enrichment_dicts})

        source_bundle_dict = source_bundle_to_dict(source_bundle)

        # Phase 1: source quality assessment
        source_dicts_for_quality = [_model_to_dict(item) for item in (fetch_result.items or [])]
        enrichment_dicts_for_quality = source_bundle_dict.get("enriched_sources") or []
        quality_report = assess_source_quality(source_dicts_for_quality, enrichment_dicts_for_quality)
        quality_report_dict = _model_to_dict(quality_report)
        source_bundle_dict["source_quality_report"] = quality_report_dict
        source_bundle_dict["recommended_action"] = quality_report.recommended_action
        if is_quality_gate_enabled() and quality_report.recommended_action == "write_brief_only":
            source_bundle_dict["content_type_override"] = "market_brief"

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

        # Phase 1: source quality gate
        if is_quality_gate_enabled() and quality_report.recommended_action == "skip_or_manual_review":
            return {
                **base_result,
                "success": False,
                "status": "SOURCE_QUALITY_INSUFFICIENT",
                "source_quality_report": quality_report_dict,
                "errors": [{"type": "source_quality_insufficient", "reasons": quality_report.reasons, "gaps": quality_report.source_gaps}],
            }

        editorial_brief = None
        brief_validation = None
        if is_structured_brief_enabled():
            editorial_brief = build_editorial_brief(
                market=market,
                language_profile=language_profile,
                source_bundle=source_bundle_dict,
            )
            brief_validation = validate_editorial_brief(editorial_brief)
            base_result["editorial_brief"] = _model_to_dict(editorial_brief)
            base_result["brief_validation"] = _model_to_dict(brief_validation)
            source_bundle_dict["editorial_brief"] = base_result["editorial_brief"]
            source_bundle_dict["brief_validation"] = base_result["brief_validation"]
            if not brief_validation.passed:
                return {
                    **base_result,
                    "success": False,
                    "status": "NEEDS_BRIEF_REWRITE",
                    "errors": [{"type": "brief_validation_failed", "issues": [_model_to_dict(issue) for issue in brief_validation.issues]}],
                }

        article_brief = build_article_brief_for_llm(
            market=market,
            language_profile=language_profile,
            source_bundle=source_bundle_dict,
            editorial_brief=editorial_brief,
        )
        base_result["article_brief"] = article_brief
        llm_result = self._run_llm_or_fake_article(market, language_profile, source_bundle_dict, article_brief, editorial_brief, brief_validation)
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

        if is_ai_reviewer_enabled():
            ai_review = review_article(
                article=article_dict,
                editorial_brief=base_result.get("editorial_brief"),
                source_bundle=source_bundle_dict,
                source_quality_report=quality_report_dict,
                validation=validation,
                language=market.content.language,
                language_profile=language_profile,
                llm_runner=self.llm_runner,
                review_profile=market.llm.review_profile,
                overrides=llm_overrides_from_profile(self.config_registry, market.llm.review_profile),
            )
            ai_review_dict = _model_to_dict(ai_review)
            base_result["ai_review"] = ai_review_dict
            source_bundle_dict["ai_review"] = ai_review_dict

        if is_quality_report_enabled():
            article_quality_report = build_article_quality_report(
                article=article_dict,
                source_bundle=source_bundle_dict,
                validation=validation,
                ai_review=base_result.get("ai_review"),
            )
            quality_report_output = _model_to_dict(article_quality_report)
            base_result["article_quality_report"] = quality_report_output
            source_bundle_dict["article_quality_report"] = quality_report_output

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

    def _run_llm_or_fake_article(
        self,
        market,
        language_profile: dict[str, Any],
        source_bundle: dict[str, Any],
        article_brief: str | None = None,
        editorial_brief: Any | None = None,
        brief_validation: Any | None = None,
    ):
        if self.llm_runner is not None:
            brief = article_brief or build_article_brief_for_llm(
                market=market,
                language_profile=language_profile,
                source_bundle=source_bundle,
            )
            return self.llm_runner.run(
                task=market.content.task,
                language=market.content.language,
                profile=market.llm.draft_profile,
                input_data={
                    "article_brief": brief,
                    "editorial_brief": _model_to_dict(editorial_brief) if editorial_brief is not None else None,
                    "brief_validation": _model_to_dict(brief_validation) if brief_validation is not None else None,
                    "market": compact_market_for_llm(market),
                    "language_profile": compact_language_profile_for_llm(language_profile),
                    "source_bundle": compact_source_bundle_for_llm(source_bundle),
                },
                overrides=llm_overrides_from_profile(self.config_registry, market.llm.draft_profile),
            )
        return _fake_article(market, language_profile, source_bundle)

    def _validate_article(self, article: dict[str, Any], source_bundle: dict[str, Any], language_profile: dict[str, Any]) -> dict[str, dict]:
        validators = {
            "article_schema": validate_article_schema(article),
            "source_grounding": validate_source_grounding(article, source_bundle),
            "language_rules": validate_language_rules(article, language_profile),
            "depth_quality": validate_depth_quality(article, language_profile, source_bundle),
            "financial_safety": validate_financial_safety(article, language_profile),
            "notion_exportable": validate_notion_exportable(article),
        }
        return {name: _model_to_dict(result) for name, result in validators.items()}


def _fake_article(market, language_profile: dict[str, Any], source_bundle: dict[str, Any]) -> ArticleDraft:
    source = source_bundle["sources"][0]
    article_type = source_bundle.get("content_type_override") or market.content.article_type
    disclaimer = language_profile.get("risk_disclaimer") or "Informasi ini hanya untuk edukasi dan bukan rekomendasi investasi."
    required_sections = language_profile.get("required_sections") or ["Sumber", "Catatan risiko"]
    if article_type == "market_brief":
        title = f"{market.symbol}: ringkasan singkat berita terbaru"
        seo_description = f"Ringkasan singkat {market.symbol} berdasarkan sumber berita yang masih terbatas."
        body = "\n\n".join(
            [
                f"Ikhtisar singkat\nSumber yang tersedia untuk {market.symbol} masih terbatas, sehingga artikel ini disajikan sebagai ringkasan pasar, bukan analisis mendalam.",
                f"Konteks pembaca\nBerita ini perlu dibaca bersama data ekonomi lanjutan, komentar bank sentral, dan perubahan sentimen risiko global.",
                f"Batasan informasi\nBelum cukup sumber yang dapat digunakan untuk menyimpulkan dampak pasar secara luas atau arah pergerakan harga.",
                f"{required_sections[0]}\n{source.get('title')}\n{source.get('url') or source.get('canonical_url') or ''}",
                f"{required_sections[1]}\n{disclaimer}",
            ]
        )
    else:
        title = f"{market.symbol}: ringkasan berita terbaru"
        seo_description = f"Ringkasan edukatif {market.symbol} berdasarkan sumber berita yang tersedia."
        body = "\n\n".join(
            [
                f"Ikhtisar peristiwa\nArtikel dry-run ini merangkum konteks {market.symbol} berdasarkan sumber yang tersedia dan menjelaskan mengapa berita tersebut penting bagi pembaca valuta asing.",
                f"Latar belakang\nPergerakan {market.symbol} biasanya dipengaruhi oleh kombinasi data ekonomi, arah kebijakan bank sentral, arus modal, dan sentimen risiko global.",
                f"Dampak pasar\nBerita dari sumber dapat membantu pembaca memahami perubahan ekspektasi pasar, tetapi tidak cukup untuk menyimpulkan arah harga secara pasti.",
                f"Hal yang perlu dipantau\nPembaca perlu mencermati data ekonomi berikutnya, komentar bank sentral, dan perubahan sentimen terhadap dolar AS maupun rupiah.",
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
        article_type=article_type,
        risk_disclaimer=disclaimer,
        region=language_profile.get("locale") or market.content.market,
        search_intent=f"Memahami berita terbaru {market.symbol}, alasan pergerakannya, dan faktor yang perlu dipantau pembaca.",
        primary_keyword=f"{market.symbol} berita forex",
        secondary_keywords=[market.symbol, market.content.market, "rupiah", "dolar AS"],
        candidate_titles=[
            title,
            f"Apa arti berita terbaru bagi {market.symbol}?",
            f"{market.symbol}: konteks pasar dan risiko yang perlu dicermati",
        ],
        editorial_angle=f"Menjelaskan konteks berita terbaru {market.symbol} untuk pembaca ritel tanpa memberi rekomendasi transaksi.",
        key_takeaways=[
            f"{market.symbol} perlu dibaca bersama konteks sumber berita yang tersedia.",
            "Pembaca perlu mencermati data lanjutan dan perubahan sentimen risiko.",
        ],
        evergreen_context=f"{market.symbol} dipengaruhi oleh perbedaan kebijakan moneter, data inflasi, arus modal, dan sentimen risiko global.",
        editor_notes=[
            {
                "type": "readability",
                "text": "Periksa apakah pembuka cukup jelas dan apakah konteks makro perlu diperdalam sebelum publikasi.",
            }
        ],
        faq=[
            {
                "question": f"Apa yang perlu dicermati dari {market.symbol}?",
                "answer": "Cermati sumber berita, data ekonomi berikutnya, dan perubahan sentimen risiko tanpa menganggap artikel ini sebagai rekomendasi transaksi.",
            }
        ],
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
    enrichment_map = _enrichment_map(bundle.get("enriched_sources"))
    sources = []
    for source in list(bundle.get("sources") or []):
        if not isinstance(source, dict):
            continue
        raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
        source_id = str(source.get("source_id") or "")
        enrichment = enrichment_map.get(source_id, {})
        enriched_text = str(enrichment.get("extracted_text") or "").strip()
        content_limit = LLM_ENRICHED_SOURCE_CONTENT_CHAR_LIMIT if enriched_text else content_char_limit
        compact = {
            "source_id": source_id or source.get("source_id"),
            "news_id": source.get("news_id") or raw.get("news_id") or raw.get("id"),
            "provider": source.get("provider") or source.get("source"),
            "symbol": source.get("symbol"),
            "exchange": source.get("exchange"),
            "language": enrichment.get("language") or source.get("language"),
            "locale": source.get("locale"),
            "title": enrichment.get("extracted_title") or source.get("title"),
            "summary": _truncate_text(source.get("summary"), content_char_limit // 2),
            "content": _truncate_text(enriched_text or source.get("content"), content_limit),
            "content_source": "enriched_text" if enriched_text else "source_content",
            "url": source.get("url"),
            "canonical_url": source.get("canonical_url"),
            "published_at": enrichment.get("published_at") or source.get("published_at"),
            "fetched_at": source.get("fetched_at"),
        }
        if enrichment:
            compact["extraction_quality"] = enrichment.get("extraction_quality")
            compact["usable_for_deep_article"] = enrichment.get("usable_for_deep_article")
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
        "source_quality_report": dict(bundle.get("source_quality_report") or {}),
        "recommended_action": bundle.get("recommended_action"),
        "content_type_override": bundle.get("content_type_override"),
    }


def build_article_brief_for_llm(*, market: Any, language_profile: dict[str, Any], source_bundle: dict[str, Any], editorial_brief: Any | None = None) -> str:
    market_data = compact_market_for_llm(market)
    profile = compact_language_profile_for_llm(language_profile)
    compact_bundle = compact_source_bundle_for_llm(source_bundle)
    disclaimer = profile.get("risk_disclaimer") or ""
    sections = [
        _article_task_instruction(compact_bundle),
        f"language: {profile.get('language') or market_data.get('language')}",
        f"region: {profile.get('locale') or market_data.get('market')}",
        f"market: {market_data.get('market')}",
        f"symbol: {market_data.get('symbol')}",
        f"article_type: {compact_bundle.get('content_type_override') or market_data.get('article_type')}",
        f"recommended_action: {compact_bundle.get('recommended_action') or 'write_article'}",
        f"target_reader: {profile.get('audience') or 'Retail FX readers who need context before interpreting the news.'}",
        f"search_intent: Explain what happened, why it matters, and what readers should watch next.",
        f"primary_keyword: {market_data.get('symbol')} berita forex",
        f"risk_disclaimer: {disclaimer}",
        "",
        "EDITORIAL_BRIEF:",
        *_editorial_brief_lines(editorial_brief),
        *_source_quality_brief_lines(compact_bundle),
        "",
        "REQUIRED_BODY_SECTIONS:",
        _required_body_sections(compact_bundle),
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
                f"content_source: {source.get('content_source')}",
                f"extraction_quality: {source.get('extraction_quality')}",
                f"title: {title}",
                f"content: {content}",
                "",
            ]
        )

    sections.extend(
        [
            "REQUIRED_JSON_FIELDS:",
            "title, slug, summary, body, seo_title, seo_description, language, market, symbol, article_type, risk_disclaimer, faq, sources_used, uncertain_claims",
            "RECOMMENDED_JSON_FIELDS:",
            "region, search_intent, primary_keyword, secondary_keywords, candidate_titles, editorial_angle, key_takeaways, evergreen_context, editor_notes",
        ]
    )
    return "\n".join(sections).strip()


def is_structured_brief_enabled() -> bool:
    return os.getenv("ENABLE_STRUCTURED_BRIEF", "0").strip().lower() in ("1", "true", "yes")


def is_quality_report_enabled() -> bool:
    return os.getenv("ENABLE_QUALITY_REPORT", "0").strip().lower() in ("1", "true", "yes")


def _editorial_brief_lines(editorial_brief: Any | None) -> list[str]:
    if editorial_brief is None:
        return [
            "- Lead with the concrete news event from the sources.",
            "- Add background context that helps readers understand the FX impact.",
            "- Explain potential market implications carefully without trading advice.",
            "- Include reader-friendly takeaways and FAQ.",
            "- Keep all factual claims grounded in the merged sources.",
        ]
    return format_editorial_brief_for_prompt(editorial_brief).splitlines()[1:]


def _enrichment_map(enriched_sources: Any) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in list(enriched_sources or []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        if source_id:
            mapping[source_id] = item
    return mapping


def _article_task_instruction(source_bundle: dict[str, Any]) -> str:
    if source_bundle.get("content_type_override") == "market_brief":
        return "TASK: Write a concise FX market brief ArticleDraft for human editorial review. Do not present it as a deep article."
    return "TASK: Write a deep, readable FX news explainer ArticleDraft for human editorial review."


def _required_body_sections(source_bundle: dict[str, Any]) -> str:
    if source_bundle.get("content_type_override") == "market_brief":
        return "Ikhtisar singkat, Konteks pembaca, Batasan informasi, Sumber, Catatan risiko"
    return "Ikhtisar peristiwa, Latar belakang, Dampak pasar, Hal yang perlu dipantau, Sumber, Catatan risiko"


def _source_quality_brief_lines(source_bundle: dict[str, Any]) -> list[str]:
    report = source_bundle.get("source_quality_report") if isinstance(source_bundle.get("source_quality_report"), dict) else {}
    if not report:
        return []
    lines = [
        f"- Source quality: {report.get('overall_source_quality')} / action: {report.get('recommended_action')}.",
    ]
    gaps = [str(gap) for gap in report.get("source_gaps") or []]
    if gaps:
        lines.append("- Explicitly acknowledge source gaps: " + ", ".join(gaps) + ".")
    if source_bundle.get("content_type_override") == "market_brief":
        lines.append("- Because sources are weak, avoid background expansion that is not directly supported by the sources.")
    return lines


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
        "audience": profile.get("audience"),
        "tone": profile.get("tone"),
        "required_sections": list(profile.get("required_sections") or []),
        "risk_disclaimer": profile.get("risk_disclaimer"),
        "forbidden_phrases": list(profile.get("forbidden_phrases") or []),
    }


def llm_overrides_from_profile(config_registry: Any, profile_name: str | None) -> dict[str, Any]:
    if not profile_name:
        return {}
    profiles = getattr(getattr(config_registry, "llm_profiles", None), "profiles", {}) or {}
    profile = profiles.get(profile_name)
    if profile is None:
        return {}
    model = _configured_model(profile)
    overrides = {
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "top_p": profile.top_p,
    }
    if model:
        overrides["model"] = model
    return {key: value for key, value in overrides.items() if value is not None}


def _configured_model(profile: Any) -> str:
    env = _local_env()
    for env_name in [getattr(profile, "model_env", None), getattr(profile, "fallback_model_env", None)]:
        if env_name:
            value = os.getenv(env_name) or env.get(env_name)
            if value:
                return str(value).strip()
    return str(getattr(profile, "fallback_model_value", "") or "").strip()


def _local_env() -> dict[str, str]:
    try:
        from src.config.loader import load_local_env
    except Exception:
        return {}
    try:
        return load_local_env()
    except Exception:
        return {}


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
