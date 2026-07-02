from __future__ import annotations

from pydantic import BaseModel, Field

from src.review.feedback import ReviewFeedback, create_review_feedback


DEFAULT_PROPERTY_MAP = {
    "status": "Status",
    "review_notes": "Review Notes",
    "editor_notes": "Editor Notes",
    "editor_score": "Editor Score",
    "rejection_reason": "Rejection Reason",
    "edited_headline": "Edited Headline",
    "edited_summary": "Edited Summary",
    "final_publish_decision": "Final Publish Decision",
    "reviewed_at": "Reviewed At",
    "quality_score": "Quality Score",
    "factuality_score": "Factuality Score",
    "language_score": "Language Score",
    "seo_score": "SEO Score",
    "compliance_score": "Compliance Score",
    "content_job_key": "Content Job Key",
    "source_bundle_hash": "Source Bundle Hash",
    "pipeline_run_id": "Pipeline Run ID",
    "market": "Market",
    "symbol": "Symbol",
    "language": "Language",
    "task": "Article Type",
    "model": "LLM Model",
    "prompt_version": "Prompt Version",
}


class NotionReviewSyncResult(BaseModel):
    success: bool
    target_name: str
    scanned: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    feedback_ids: list[str] = Field(default_factory=list)


class NotionReviewSyncer:
    def __init__(self, target_resolver, notion_client, feedback_store):
        self.target_resolver = target_resolver
        self.notion_client = notion_client
        self.feedback_store = feedback_store

    def sync(
        self,
        *,
        target_name: str,
        reviewer: str | None = None,
        status_filter: list[str] | None = None,
        page_size: int = 50,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> NotionReviewSyncResult:
        target = self.target_resolver.resolve(target_name)
        if target.parent_type != "data_source":
            return NotionReviewSyncResult(success=False, target_name=target_name, errors=[{"type": "review_sync_requires_data_source_parent"}])
        if not target.parent_id:
            return NotionReviewSyncResult(success=False, target_name=target_name, errors=[{"type": "missing_notion_parent_id"}], warnings=list(target.warnings or []))

        result = NotionReviewSyncResult(success=True, target_name=target_name, warnings=list(target.warnings or []))
        cursor = None
        while True:
            query = self.notion_client.query_data_source(data_source_id=target.parent_id, page_size=page_size, start_cursor=cursor)
            if not query.success:
                result.success = False
                result.errors.append({"type": "notion_query_failed", "error": _api_error_dict(query.error)})
                return result
            data = query.data or {}
            pages = data.get("results") if isinstance(data.get("results"), list) else []
            for page in pages:
                if limit is not None and result.scanned >= limit:
                    return result
                result.scanned += 1
                try:
                    feedback = notion_page_to_review_feedback(page, reviewer=reviewer)
                    if feedback is None or _status_filtered(feedback.review_status if feedback else None, status_filter):
                        result.skipped += 1
                        continue
                    if not dry_run and _already_exists(self.feedback_store, feedback):
                        result.skipped += 1
                        continue
                    if not dry_run:
                        self.feedback_store.append(feedback)
                    result.imported += 1
                    result.feedback_ids.append(feedback.feedback_id)
                except Exception as exc:
                    result.errors.append({"type": "page_parse_error", "message": str(exc), "page_id": page.get("id") if isinstance(page, dict) else None})
            if not data.get("has_more") or not data.get("next_cursor"):
                return result
            cursor = data.get("next_cursor")


def get_property(properties: dict, name: str) -> dict | None:
    try:
        prop = properties.get(name)
    except AttributeError:
        return None
    return prop if isinstance(prop, dict) else None


def extract_title(prop: dict | None) -> str | None:
    return _extract_text_array(prop, "title")


def extract_rich_text(prop: dict | None) -> str | None:
    return _extract_text_array(prop, "rich_text")


def extract_select(prop: dict | None) -> str | None:
    try:
        select = prop.get("select")
        return select.get("name") if isinstance(select, dict) else None
    except AttributeError:
        return None


def extract_number(prop: dict | None) -> int | float | None:
    try:
        number = prop.get("number")
    except AttributeError:
        return None
    return number if isinstance(number, (int, float)) else None


def extract_url(prop: dict | None) -> str | None:
    try:
        url = prop.get("url")
    except AttributeError:
        return None
    return url if isinstance(url, str) else None


def extract_date(prop: dict | None) -> str | None:
    try:
        date = prop.get("date")
        return date.get("start") if isinstance(date, dict) else None
    except AttributeError:
        return None


def map_notion_status_to_review_status(status: str | None) -> str | None:
    if not status:
        return None
    normalized = str(status).strip().lower().replace("_", " ")
    mapping = {
        "approved": "approved",
        "published": "published",
        "rejected": "rejected",
        "needs edit": "needs_edit",
        "needs rewrite": "needs_rewrite",
        "needs source fix": "needs_source_fix",
        "needs compliance fix": "needs_compliance_fix",
        "needs language fix": "needs_language_fix",
        "ignored": "ignored",
        "ai draft": None,
        "needs review": None,
        "in review": None,
    }
    return mapping.get(normalized)


def notion_page_to_review_feedback(
    page: dict,
    *,
    reviewer: str | None = None,
    property_map: dict | None = None,
) -> ReviewFeedback | None:
    prop_map = {**DEFAULT_PROPERTY_MAP, **(property_map or {})}
    properties = page.get("properties") if isinstance(page.get("properties"), dict) else {}
    status = map_notion_status_to_review_status(extract_select(get_property(properties, prop_map["status"])))
    if status is None:
        return None

    metadata = {"notion_sync": True, "warnings": []}
    editor_score = _safe_score(extract_number(get_property(properties, prop_map["editor_score"])), "editor_score", metadata)
    scores = {
        "editor_score": editor_score,
        "quality_score": _safe_score(extract_number(get_property(properties, prop_map["quality_score"])), "quality_score", metadata),
        "factuality_score": _safe_score(extract_number(get_property(properties, prop_map["factuality_score"])), "factuality_score", metadata),
        "language_score": _safe_score(extract_number(get_property(properties, prop_map["language_score"])), "language_score", metadata),
        "seo_score": _safe_score(extract_number(get_property(properties, prop_map["seo_score"])), "seo_score", metadata),
        "compliance_score": _safe_score(extract_number(get_property(properties, prop_map["compliance_score"])), "compliance_score", metadata),
    }
    return create_review_feedback(
        review_status=status,
        pipeline_run_id=extract_rich_text(get_property(properties, prop_map["pipeline_run_id"])),
        content_job_key=extract_rich_text(get_property(properties, prop_map["content_job_key"])),
        source_bundle_hash=extract_rich_text(get_property(properties, prop_map["source_bundle_hash"])),
        notion_page_id=page.get("id"),
        notion_url=page.get("url"),
        market_id=extract_select(get_property(properties, prop_map["market"])) or extract_rich_text(get_property(properties, prop_map["market"])),
        symbol=extract_select(get_property(properties, prop_map["symbol"])) or extract_rich_text(get_property(properties, prop_map["symbol"])),
        language=extract_select(get_property(properties, prop_map["language"])) or extract_rich_text(get_property(properties, prop_map["language"])),
        task=extract_select(get_property(properties, prop_map["task"])) or extract_rich_text(get_property(properties, prop_map["task"])),
        model=extract_rich_text(get_property(properties, prop_map["model"])),
        prompt_version=extract_rich_text(get_property(properties, prop_map["prompt_version"])),
        reviewer=reviewer,
        notes=_first_text_property(properties, [prop_map["editor_notes"], prop_map["review_notes"]]),
        rejection_reason=extract_rich_text(get_property(properties, prop_map["rejection_reason"])),
        edited_headline=extract_rich_text(get_property(properties, prop_map["edited_headline"])),
        edited_summary=extract_rich_text(get_property(properties, prop_map["edited_summary"])),
        final_publish_decision=extract_select(get_property(properties, prop_map["final_publish_decision"])) or extract_rich_text(get_property(properties, prop_map["final_publish_decision"])),
        reviewed_at=extract_date(get_property(properties, prop_map["reviewed_at"])),
        metadata=metadata,
        **scores,
    )


def _extract_text_array(prop: dict | None, key: str) -> str | None:
    try:
        items = prop.get(key)
    except AttributeError:
        return None
    if not isinstance(items, list):
        return None
    text = "".join(str(item.get("plain_text") or item.get("text", {}).get("content") or "") for item in items if isinstance(item, dict))
    return text or None


def _safe_score(value, field_name: str, metadata: dict) -> int | None:
    if value is None:
        return None
    score = int(value)
    if not 1 <= score <= 5:
        metadata["warnings"].append({"type": "invalid_review_score", "field": field_name, "value": value})
        return None
    return score


def _first_text_property(properties: dict, names: list[str]) -> str | None:
    for name in names:
        value = extract_rich_text(get_property(properties, name))
        if value:
            return value
    return None


def _status_filtered(review_status: str | None, status_filter: list[str] | None) -> bool:
    if not status_filter:
        return False
    normalized = {str(item).strip().lower().replace("_", " ") for item in status_filter}
    return str(review_status or "").replace("_", " ") not in normalized and str(review_status or "") not in status_filter


def _already_exists(feedback_store, feedback: ReviewFeedback) -> bool:
    if feedback.notion_page_id and feedback_store.latest_by_notion_page_id(feedback.notion_page_id):
        return True
    if feedback.content_job_key and feedback_store.latest_by_content_job_key(feedback.content_job_key):
        return True
    return False


def _api_error_dict(error) -> dict:
    if error is None:
        return {"type": "notion_api_error", "message": "Unknown Notion API error."}
    if hasattr(error, "model_dump"):
        return error.model_dump()
    if hasattr(error, "dict"):
        return error.dict()
    return dict(error)
