from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any

from src.content.validators._utils import parse_article
from src.notion.target_resolver import ResolvedNotionTarget


MAX_RICH_TEXT_CONTENT = 1800


def chunk_text(text: str, max_length: int = 1800) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    chunks: list[str] = []
    for paragraph in [part.strip() for part in value.split("\n\n") if part.strip()]:
        if len(paragraph) <= max_length:
            chunks.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            chunks.append(paragraph[start : start + max_length])
            start += max_length
    return chunks


class NotionPropertyMapper:
    def build_properties(
        self,
        *,
        article,
        market,
        language_profile,
        source_bundle,
        validation: dict | None = None,
        llm: dict | None = None,
        pipeline_run_id: str | None = None,
        content_job_key: str | None = None,
        source_bundle_hash: str | None = None,
        target: ResolvedNotionTarget | None = None,
    ) -> dict:
        parsed = parse_article(article)
        profile = _as_dict(language_profile)
        notion_fields = profile.get("notion") or {}
        llm_data = llm or {}
        run_id = pipeline_run_id or _stable_pipeline_run_id(parsed, source_bundle)
        bundle_hash = source_bundle_hash or str((source_bundle or {}).get("source_bundle_hash") or (source_bundle or {}).get("bundle_id") or "")
        source_urls = [source.url for source in parsed.sources_used if source.url]
        return {
            notion_fields.get("title_property", "Name"): _title(parsed.title),
            notion_fields.get("status_property", "Status"): _status((target.reviewer_status if target else None) or "Needs Review"),
            notion_fields.get("language_property", "Language"): _select(parsed.language),
            notion_fields.get("market_property", "Market"): _select(parsed.market or getattr(getattr(market, "content", None), "market", "")),
            notion_fields.get("symbol_property", "Symbol"): _rich_text_property(parsed.symbol or getattr(market, "symbol", "")),
            "Article Type": _select(parsed.article_type),
            "AI Summary": _rich_text_property(parsed.summary),
            "SEO Title": _rich_text_property(parsed.seo_title),
            "SEO Description": _rich_text_property(parsed.seo_description),
            "Search Intent": _rich_text_property(parsed.search_intent),
            "Primary Keyword": _rich_text_property(parsed.primary_keyword),
            "Candidate Titles": _rich_text_property("\n".join(parsed.candidate_titles)),
            "Source Count": {"number": len(parsed.sources_used)},
            "Source URLs": _rich_text_property("\n".join(source_urls)),
            "Usable Source Count": {"number": _source_quality_field(source_bundle, "usable_source_count", 0)},
            "Source Quality": _select(_source_quality_field(source_bundle, "overall_source_quality", "unknown")),
            "Brief Content Type": _select(_brief_field(source_bundle, "content_type", parsed.article_type or "unknown")),
            "Brief Confidence": _select(_brief_field(source_bundle, "confidence_level", "unknown")),
            "AI Review Readiness": _select(_ai_review_field(source_bundle, "publish_readiness", "not_run")),
            "AI Grounding Score": {"number": _ai_review_score(source_bundle, "grounding", 0)},
            "AI Depth Score": {"number": _ai_review_score(source_bundle, "depth", 0)},
            "AI Financial Safety Score": {"number": _ai_review_score(source_bundle, "financial_safety", 0)},
            "Editor Ready Score": {"number": _quality_report_field(source_bundle, "editor_ready_score", 0)},
            "Final Recommended Status": _select(_quality_report_field(source_bundle, "final_recommended_status", "not_run")),
            "Risk Level": _select(_risk_level(validation)),
            "Prompt Version": _rich_text_property(str(llm_data.get("prompt_version") or "")),
            "LLM Model": _rich_text_property(str(llm_data.get("model") or "")),
            "Content Job Key": _rich_text_property(str(content_job_key or "")),
            "Source Bundle Hash": _rich_text_property(bundle_hash),
            "Pipeline Run ID": _rich_text_property(run_id),
            "Generated At": {"date": {"start": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}},
        }


class NotionBlockBuilder:
    def build_blocks(
        self,
        *,
        article,
        source_bundle,
        validation: dict | None = None,
        llm: dict | None = None,
    ) -> list[dict]:
        parsed = parse_article(article)
        blocks: list[dict] = [
            _heading(2, "Review Note"),
            _paragraph("AI-generated draft for human review. Do not publish without approval."),
            _heading(2, "AI Summary"),
            _paragraph(parsed.summary),
            _heading(2, "Editorial Brief"),
            *_editorial_brief_blocks(source_bundle, parsed),
            _heading(2, "Source Quality"),
            *_source_quality_blocks(source_bundle),
            _heading(2, "AI Review"),
            *_ai_review_blocks(source_bundle),
            _heading(2, "Article Quality Report"),
            *_article_quality_report_blocks(source_bundle),
            _heading(2, "Article Body"),
        ]
        for chunk in chunk_text(parsed.body):
            blocks.append(_paragraph(chunk))

        blocks.append(_heading(2, "FAQ"))
        if parsed.faq:
            for item in parsed.faq:
                blocks.append(_heading(3, item.question))
                blocks.append(_paragraph(item.answer))
        else:
            blocks.append(_paragraph("No FAQ items."))

        blocks.append(_heading(2, "Sources"))
        for source in parsed.sources_used:
            parts = [source.title]
            if source.provider:
                parts.append(f"Provider: {source.provider}")
            if source.url:
                parts.append(source.url)
            blocks.append(_bulleted_item(" | ".join(part for part in parts if part)))

        blocks.extend(
            [
                _heading(2, "Risk Disclaimer"),
                _paragraph(parsed.risk_disclaimer),
                _heading(2, "Editor Notes"),
                *_editor_note_blocks(parsed),
                _heading(2, "Validation Results"),
            ]
        )
        blocks.extend(_validation_blocks(validation or {}))
        blocks.extend(
            [
                _heading(2, "Generation Metadata"),
                _paragraph(_json_text({"llm": llm or {}, "source_trace": (source_bundle or {}).get("source_trace") or {}})),
            ]
        )
        return blocks


def _validation_blocks(validation: dict) -> list[dict]:
    if not validation:
        return [_paragraph("No validation metadata.")]
    blocks: list[dict] = []
    for name, result in validation.items():
        issues = result.get("issues") or []
        blocks.append(_bulleted_item(f"{name}: passed={bool(result.get('passed'))}, issues={len(issues)}"))
        for issue in issues:
            blocks.append(_bulleted_item(f"- {issue.get('severity')}: {issue.get('code')} - {issue.get('message')}"))
    return blocks


def _stable_pipeline_run_id(article, source_bundle: dict) -> str:
    basis = "|".join(
        [
            article.symbol,
            article.language,
            str((source_bundle or {}).get("source_bundle_hash") or (source_bundle or {}).get("bundle_id") or ""),
            article.slug,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _risk_level(validation: dict | None) -> str:
    if not validation:
        return "low"
    if any(issue.get("severity") == "error" for result in validation.values() for issue in result.get("issues", [])):
        return "high"
    if any(issue.get("severity") == "warning" for result in validation.values() for issue in result.get("issues", [])):
        return "medium"
    return "low"


def _source_quality_blocks(source_bundle: dict | None) -> list[dict]:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    report = bundle.get("source_quality_report")
    if not isinstance(report, dict):
        return [_paragraph("No source quality report available.")]
    blocks = [
        _bulleted_item(f"Source quality: {report.get('overall_source_quality', 'unknown')}"),
        _bulleted_item(f"Usable sources: {report.get('usable_source_count', 0)} / {report.get('source_count', 0)}"),
        _bulleted_item(f"Avg text length: {report.get('average_text_length', 0)}"),
        _bulleted_item(f"Extraction success rate: {report.get('extraction_success_rate', 0)}"),
        _bulleted_item(f"Recommended action: {report.get('recommended_action', 'unknown')}"),
    ]
    for reason in report.get("reasons") or []:
        blocks.append(_bulleted_item(f"Reason: {reason}"))
    for gap in report.get("source_gaps") or []:
        blocks.append(_bulleted_item(f"Gap: {gap}"))
    return blocks


def _source_quality_field(source_bundle: dict | None, field: str, default: Any = None) -> Any:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    report = bundle.get("source_quality_report")
    if isinstance(report, dict):
        return report.get(field, default)
    return default


def _brief_field(source_bundle: dict | None, field: str, default: Any = None) -> Any:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    brief = bundle.get("editorial_brief")
    if isinstance(brief, dict):
        return brief.get(field, default)
    return default


def _editorial_brief_blocks(source_bundle: dict | None, article) -> list[dict]:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    brief = bundle.get("editorial_brief")
    if not isinstance(brief, dict):
        return [_paragraph(_editorial_summary(article))]

    blocks = [
        _bulleted_item(f"Content type: {brief.get('content_type', 'unknown')}"),
        _bulleted_item(f"Confidence: {brief.get('confidence_level', 'unknown')}"),
        _bulleted_item(f"Primary angle: {brief.get('primary_angle', '')}"),
        _bulleted_item(f"Event summary: {brief.get('event_summary', '')}"),
        _bulleted_item(f"Why it matters: {brief.get('why_it_matters', '')}"),
        _bulleted_item(f"Market context: {brief.get('market_context', '')}"),
        _bulleted_item(f"Target reader: {brief.get('target_reader', '')}"),
    ]
    blocks.extend(_list_value_blocks("Reader question", brief.get("reader_questions")))
    blocks.extend(_list_value_blocks("Must cover", brief.get("must_cover")))
    blocks.extend(_list_value_blocks("Avoid claim", brief.get("avoid_claims")))
    blocks.extend(_list_value_blocks("Source gap", brief.get("source_gaps")))
    blocks.extend(_list_value_blocks("Recommended section", brief.get("recommended_structure")))

    validation = bundle.get("brief_validation")
    if isinstance(validation, dict):
        blocks.append(_bulleted_item(f"Brief validation: {validation.get('recommended_status', 'unknown')}"))
        for issue in validation.get("issues") or []:
            if isinstance(issue, dict):
                blocks.append(_bulleted_item(f"Brief issue: {issue.get('severity')} - {issue.get('code')} - {issue.get('message')}"))
    return blocks


def _ai_review_field(source_bundle: dict | None, field: str, default: Any = None) -> Any:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    review = bundle.get("ai_review")
    if isinstance(review, dict):
        return review.get(field, default)
    return default


def _ai_review_score(source_bundle: dict | None, field: str, default: int = 0) -> int:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    review = bundle.get("ai_review")
    scores = review.get("scores") if isinstance(review, dict) else {}
    if isinstance(scores, dict):
        value = scores.get(field, default)
        return int(value or 0)
    return default


def _ai_review_blocks(source_bundle: dict | None) -> list[dict]:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    review = bundle.get("ai_review")
    if not isinstance(review, dict):
        return [_paragraph("AI reviewer was not run.")]
    scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}
    blocks = [
        _bulleted_item(f"Readiness: {review.get('publish_readiness', 'unknown')}"),
        _bulleted_item(f"Reviewer mode: {review.get('reviewer_mode', 'unknown')}"),
        _bulleted_item(f"Recommended editor action: {review.get('recommended_editor_action', '')}"),
        _bulleted_item(
            "Scores: "
            + ", ".join(
                [
                    f"grounding={scores.get('grounding', 0)}",
                    f"depth={scores.get('depth', 0)}",
                    f"readability={scores.get('readability', 0)}",
                    f"headline={scores.get('headline_quality', 0)}",
                    f"financial_safety={scores.get('financial_safety', 0)}",
                    f"source_usefulness={scores.get('source_usefulness', 0)}",
                ]
            )
        ),
    ]
    blocks.extend(_list_value_blocks("Unsupported claim", review.get("unsupported_claims")))
    blocks.extend(_list_value_blocks("Overstatement", review.get("overstatements")))
    blocks.extend(_list_value_blocks("Missing context", review.get("missing_context")))
    for issue in review.get("issues") or []:
        if isinstance(issue, dict):
            blocks.append(_bulleted_item(f"Issue: {issue.get('severity')} - {issue.get('issue_type')} - {issue.get('description')}"))
    return blocks


def _quality_report_field(source_bundle: dict | None, field: str, default: Any = None) -> Any:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    report = bundle.get("article_quality_report")
    if isinstance(report, dict):
        return report.get(field, default)
    return default


def _article_quality_report_blocks(source_bundle: dict | None) -> list[dict]:
    bundle = source_bundle if isinstance(source_bundle, dict) else {}
    report = bundle.get("article_quality_report")
    if not isinstance(report, dict):
        return [_paragraph("Article quality report was not generated.")]
    blocks = [
        _bulleted_item(f"Final status: {report.get('final_recommended_status', 'unknown')}"),
        _bulleted_item(f"Editor ready score: {report.get('editor_ready_score', 0)}"),
        _bulleted_item(f"Sources: usable={report.get('usable_source_count', 0)} / total={report.get('source_count', 0)}"),
        _bulleted_item(f"Body length: {report.get('body_length', 0)}"),
        _bulleted_item(f"FAQ count: {report.get('faq_count', 0)}"),
        _bulleted_item(f"Market context: {bool(report.get('has_market_context'))}"),
        _bulleted_item(f"Risk disclaimer: {bool(report.get('has_risk_disclaimer'))}"),
        _bulleted_item(f"Source attribution: {bool(report.get('has_source_attribution'))}"),
        _bulleted_item(f"Headline risk: {report.get('headline_risk_level', 'unknown')}"),
        _bulleted_item(f"Financial advice detected: {bool(report.get('financial_advice_detected'))}"),
    ]
    if report.get("grounded_claim_ratio") is not None:
        blocks.append(_bulleted_item(f"Grounded claim ratio: {report.get('grounded_claim_ratio')}"))
    blocks.extend(_list_value_blocks("Blocking issue", report.get("blocking_issues")))
    blocks.extend(_list_value_blocks("Warning", report.get("warnings")))
    return blocks


def _list_value_blocks(label: str, values: Any) -> list[dict]:
    if not isinstance(values, list):
        return []
    return [_bulleted_item(f"{label}: {value}") for value in values if value]


def _editorial_summary(article) -> str:
    parts = []
    if article.search_intent:
        parts.append(f"Search intent: {article.search_intent}")
    if article.primary_keyword:
        parts.append(f"Primary keyword: {article.primary_keyword}")
    if article.secondary_keywords:
        parts.append("Secondary keywords: " + ", ".join(article.secondary_keywords))
    if article.editorial_angle:
        parts.append(f"Editorial angle: {article.editorial_angle}")
    if article.key_takeaways:
        parts.append("Key takeaways:\n" + "\n".join(f"- {item}" for item in article.key_takeaways))
    if article.candidate_titles:
        parts.append("Candidate titles:\n" + "\n".join(f"- {item}" for item in article.candidate_titles))
    if article.evergreen_context:
        parts.append(f"Evergreen context: {article.evergreen_context}")
    return "\n\n".join(parts) if parts else "No editorial brief metadata."


def _editor_note_blocks(article) -> list[dict]:
    if not article.editor_notes:
        return [_paragraph("No editor notes.")]
    return [_bulleted_item(f"{note.type}: {note.text}") for note in article.editor_notes]


def _title(text: str) -> dict:
    return {"title": [{"text": {"content": str(text or "")[:MAX_RICH_TEXT_CONTENT]}}]}


def _status(name: str) -> dict:
    return {"status": {"name": name}}


def _select(name: str) -> dict:
    return {"select": {"name": str(name or "")}}


def _rich_text_property(text: str) -> dict:
    value = str(text or "")[:MAX_RICH_TEXT_CONTENT]
    return {"rich_text": [{"text": {"content": value}}] if value else []}


def _rich_text(text: Any) -> list[dict]:
    value = str(text or "")[:MAX_RICH_TEXT_CONTENT]
    return [{"text": {"content": value}}] if value else []


def _paragraph(text: Any) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _heading(level: int, text: Any) -> dict:
    block_type = f"heading_{level}"
    return {"object": "block", "type": block_type, block_type: {"rich_text": _rich_text(text)}}


def _bulleted_item(text: Any) -> dict:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_text(text)}}


def _json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _as_dict(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if is_dataclass(value):
        return asdict(value)
    return dict(value)
