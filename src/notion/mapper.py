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
            "Source Count": {"number": len(parsed.sources_used)},
            "Source URLs": _rich_text_property("\n".join(source_urls)),
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
