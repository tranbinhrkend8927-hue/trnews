"""Export approved generated articles to Notion."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import requests

from draft_quality import evaluate_draft_quality
from notion_config import get_notion_parent, json_safe, load_notion_config
from safety_validation import validate_financial_safety


NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
MAX_NOTION_CHILDREN_PER_APPEND = 100
MAX_RICH_TEXT_CONTENT = 1800
MAX_PARAGRAPH_CHARS = 1800
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRY_STATUS_CODES = {400, 401, 403}
EXPORT_POLICY_SKIP_EXISTING = "skip_existing"
EXPORT_POLICY_RETRY_FAILED = "retry_failed"
EXPORT_POLICY_FORCE_REEXPORT = "force_reexport"
EXPORT_POLICIES = {
    EXPORT_POLICY_SKIP_EXISTING,
    EXPORT_POLICY_RETRY_FAILED,
    EXPORT_POLICY_FORCE_REEXPORT,
}


def _error(error_type: str, message: str, *, retryable: bool = False, **extra: Any) -> Dict[str, Any]:
    payload = {"type": error_type, "message": message, "retryable": bool(retryable)}
    payload.update(extra)
    return json_safe(payload)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rich_text(content: Any) -> List[Dict[str, Any]]:
    text = _text(content)
    if not text:
        return []
    return [{"text": {"content": text[:MAX_RICH_TEXT_CONTENT]}}]


def _paragraph(content: Any) -> Dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(content)}}


def _heading(level: int, content: Any) -> Dict[str, Any]:
    block_type = f"heading_{level}"
    return {"object": "block", "type": block_type, block_type: {"rich_text": _rich_text(content)}}


def _bulleted_item(content: Any) -> Dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_text(content)}}


def _chunk_text(value: Any, max_chars: int = MAX_PARAGRAPH_CHARS) -> List[str]:
    text = _text(value)
    if not text:
        return []
    paragraphs: List[str] = []
    for part in [item.strip() for item in text.split("\n\n") if item.strip()]:
        if len(part) <= max_chars:
            paragraphs.append(part)
            continue
        start = 0
        while start < len(part):
            paragraphs.append(part[start : start + max_chars])
            start += max_chars
    return paragraphs


def _parse_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return json_safe(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return json_safe(loaded if isinstance(loaded, dict) else {})
    return {}


def _source_bundle_from_article(article: Dict[str, Any], article_sources: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    sources = [
        {
            "source_type": source.get("source_type"),
            "source": source.get("source_name"),
            "source_name": source.get("source_name"),
            "url": source.get("source_url"),
            "source_url": source.get("source_url"),
            "title": source.get("cited_claim"),
            "summary": source.get("cited_claim"),
        }
        for source in (article_sources or [])
        if source
    ]
    sources_json = _parse_json_object((article or {}).get("sources_json"))
    bundled = sources_json.get("source_bundle") if isinstance(sources_json.get("source_bundle"), dict) else sources_json
    return json_safe(
        {
            "topic_id": bundled.get("topic_id") or article.get("topic_id"),
            "topic_type": bundled.get("topic_type"),
            "symbol": article.get("symbol") or bundled.get("symbol"),
            "source_news_ids": bundled.get("source_news_ids") or [],
            "sources": sources,
            "missing_source_news_ids": bundled.get("missing_source_news_ids") or [],
            "warnings": bundled.get("warnings") or [],
            "errors": bundled.get("errors") or [],
        }
    )


def fetch_article_for_export(dsn: str, article_id: int) -> Optional[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, topic_id, symbol, language, title, slug, summary, body,
                    seo_title, seo_description, status, fact_check_status,
                    risk_disclaimer_included, sources_json, created_at, updated_at,
                    published_at
                FROM generated_articles
                WHERE id = %s
                LIMIT 1
                """,
                (article_id,),
            )
            row = cur.fetchone()
            return json_safe(row) if row else None


def fetch_article_sources_for_export(dsn: str, article_id: int) -> List[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, source_type, source_name, source_url, cited_claim, created_at
                FROM article_sources
                WHERE article_id = %s
                ORDER BY id
                """,
                (article_id,),
            )
            return json_safe(cur.fetchall())


def fetch_article_export_history(dsn: str, article_id: int, target: str = "notion") -> List[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id, article_id, target, target_id, target_url, status,
                        request_json, response_json, error_json, exported_at, created_at
                    FROM article_exports
                    WHERE article_id = %s
                      AND target = %s
                    ORDER BY created_at DESC NULLS LAST, id DESC
                    """,
                    (article_id, target),
                )
                return json_safe(cur.fetchall())
    except Exception as exc:
        return [{"status": "error", "error": _error("db_error", str(exc))}]


def determine_export_action(
    export_history: List[Dict[str, Any]],
    policy: str = EXPORT_POLICY_SKIP_EXISTING,
) -> Dict[str, Any]:
    export_history = json_safe(list(export_history or []))
    policy = _text(policy) or EXPORT_POLICY_SKIP_EXISTING
    warnings: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    if policy not in EXPORT_POLICIES:
        blockers.append(_error("invalid_export_policy", "Unsupported export policy.", policy=policy))
        return json_safe(
            {
                "action": "skip",
                "can_export": False,
                "policy": policy,
                "existing_export": {},
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    history_error = next((item for item in export_history if item.get("status") == "error" or item.get("error")), None)
    if history_error:
        blockers.append(history_error.get("error") or _error("export_history_error", "Export history could not be loaded."))
        return json_safe(
            {
                "action": "skip",
                "can_export": False,
                "policy": policy,
                "existing_export": history_error,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    exported = next((item for item in export_history if item.get("status") == "exported"), None)
    failed = next((item for item in export_history if item.get("status") == "failed"), None)
    existing = exported or failed or (export_history[0] if export_history else {})

    if not export_history:
        return json_safe(
            {
                "action": "export",
                "can_export": True,
                "policy": policy,
                "existing_export": {},
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    if exported and policy == EXPORT_POLICY_FORCE_REEXPORT:
        warnings.append(_error("force_reexport_existing_export", "Existing exported record found; force re-export will create a new Notion page."))
        return json_safe(
            {
                "action": "force_reexport",
                "can_export": True,
                "policy": policy,
                "existing_export": exported,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    if exported:
        warnings.append(_error("existing_exported_record", "Article already has an exported Notion record."))
        return json_safe(
            {
                "action": "skip",
                "can_export": False,
                "policy": policy,
                "existing_export": exported,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    if failed and policy == EXPORT_POLICY_RETRY_FAILED:
        warnings.append(_error("retry_failed_export", "Retrying a previous failed Notion export."))
        return json_safe(
            {
                "action": "retry",
                "can_export": True,
                "policy": policy,
                "existing_export": failed,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    if failed and policy == EXPORT_POLICY_FORCE_REEXPORT:
        warnings.append(_error("force_reexport_failed_export", "Force re-export requested after a failed Notion export."))
        return json_safe(
            {
                "action": "force_reexport",
                "can_export": True,
                "policy": policy,
                "existing_export": failed,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    if failed:
        warnings.append(_error("failed_export_requires_retry", "Previous failed Notion export found; pass --retry-failed to retry explicitly."))
        return json_safe(
            {
                "action": "skip",
                "can_export": False,
                "policy": policy,
                "existing_export": failed,
                "warnings": warnings,
                "blockers": blockers,
            }
        )

    return json_safe(
        {
            "action": "export",
            "can_export": True,
            "policy": policy,
            "existing_export": existing,
            "warnings": warnings,
            "blockers": blockers,
        }
    )


def validate_article_exportable(
    article: Optional[Dict[str, Any]],
    article_sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    if not article:
        return {"exportable": False, "blockers": [_error("article_not_found", "Article not found.")], "warnings": []}

    article = json_safe(article)
    article_sources = json_safe(list(article_sources or []))
    status = article.get("status")
    if status != "approved":
        blockers.append(_error("status_not_approved", "Only approved articles can be exported.", status=status))
    if status in {"pending_review", "draft", "rejected", "published"}:
        blockers.append(_error(f"status_{status}_blocked", f"Articles with status={status} cannot be exported."))
    if article.get("fact_check_status") == "failed":
        blockers.append(_error("fact_check_failed", "Articles with failed fact_check_status cannot be exported."))
    if article.get("fact_check_status") == "needs_sources":
        blockers.append(_error("fact_check_needs_sources", "Articles that need sources cannot be exported."))
    if not _text(article.get("title")):
        blockers.append(_error("missing_title", "Article title is required."))
    if not _text(article.get("body")):
        blockers.append(_error("missing_body", "Article body is required."))
    if not bool(article.get("risk_disclaimer_included")):
        blockers.append(_error("missing_risk_disclaimer", "Risk disclaimer is required."))
    if not article_sources:
        blockers.append(_error("missing_article_sources", "At least one article source is required."))

    safety_result = validate_financial_safety(article, article_sources)
    source_bundle = _source_bundle_from_article(article, article_sources)
    quality_article = dict(article)
    quality_article["status"] = "pending_review"
    quality_result = evaluate_draft_quality(quality_article, source_bundle=source_bundle, safety_result=safety_result)
    if safety_result.get("passed") is False:
        blockers.append(_error("safety_failed", "Safety validation failed."))
    if quality_result.get("level") == "blocked" or quality_result.get("blocking_issues"):
        blockers.append(_error("quality_blocked", "Quality gate is blocked."))

    if not _text(article.get("seo_title")):
        warnings.append(_error("missing_seo_title", "SEO title is missing."))
    if not _text(article.get("seo_description")):
        warnings.append(_error("missing_seo_description", "SEO description is missing."))
    if "faq" not in _text(article.get("body")).lower():
        warnings.append(_error("missing_faq", "FAQ section is missing."))
    if any(not _text(source.get("source_url")) for source in article_sources):
        warnings.append(_error("missing_source_url", "One or more article sources are missing source_url."))
    if len(_text(article.get("body"))) < 500:
        warnings.append(_error("body_short", "Article body is short."))

    return json_safe(
        {
            "exportable": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "safety_result": safety_result,
            "quality_result": quality_result,
        }
    )


def build_notion_page_properties(
    article: Dict[str, Any],
    article_sources: Optional[Iterable[Dict[str, Any]]] = None,
    parent_type: str = "data_source",
) -> Dict[str, Any]:
    article = article or {}
    source_count = len(list(article_sources or []))
    title = _text(article.get("title")) or f"Article {article.get('id')}"
    if parent_type == "page":
        return {"title": _rich_text(title)}
    return json_safe(
        {
            "Name": {"title": _rich_text(title)},
            "Status": {"select": {"name": "Approved"}},
            "Language": {"select": {"name": _text(article.get("language")) or "id"}},
            "Symbol": {"rich_text": _rich_text(article.get("symbol"))},
            "Source Count": {"number": source_count},
            "Article ID": {"number": int(article.get("id") or 0)},
        }
    )


def _faq_items(article: Dict[str, Any]) -> List[str]:
    body = _text(article.get("body"))
    items = []
    capture = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("faq"):
            capture = True
            continue
        if capture and stripped.lower().startswith(("sumber", "catatan risiko")):
            break
        if capture and stripped:
            items.append(stripped)
    return items


def build_notion_blocks(
    article: Dict[str, Any],
    article_sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    article = article or {}
    article_sources = list(article_sources or [])
    blocks: List[Dict[str, Any]] = [
        _heading(1, article.get("title")),
        _paragraph(article.get("summary")),
        _heading(2, "Artikel"),
    ]
    blocks.extend(_paragraph(part) for part in _chunk_text(article.get("body")))
    blocks.append(_heading(2, "FAQ"))
    faq_items = _faq_items(article)
    if faq_items:
        blocks.extend(_bulleted_item(item) for item in faq_items)
    else:
        blocks.append(_paragraph("FAQ belum tersedia."))
    blocks.append(_heading(2, "Sumber"))
    for source in article_sources:
        claim = _text(source.get("cited_claim")) or _text(source.get("source_name")) or "Sumber"
        url = _text(source.get("source_url"))
        blocks.append(_bulleted_item(f"{claim} - {url}" if url else claim))
    blocks.append(_heading(2, "Catatan risiko"))
    risk_disclaimer = _text(article.get("risk_disclaimer")) or "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."
    blocks.append(_paragraph(risk_disclaimer))
    return json_safe(blocks)


def _request_summary(parent_type: str, properties: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    return json_safe(
        {
            "target": "notion",
            "parent_type": parent_type,
            "property_keys": sorted(properties.keys()),
            "block_count": len(blocks),
        }
    )


def _response_summary(response: Dict[str, Any]) -> Dict[str, Any]:
    return json_safe(
        {
            "id": response.get("id"),
            "url": response.get("url"),
            "object": response.get("object"),
        }
    )


class NotionClient:
    def __init__(
        self,
        api_key: str,
        *,
        data_source_id: Optional[str] = None,
        parent_page_id: Optional[str] = None,
        timeout_seconds: int = 60,
        max_retries: int = 2,
        session: Any = None,
    ) -> None:
        self.api_key = api_key
        self.data_source_id = data_source_id
        self.parent_page_id = parent_page_id
        self.timeout_seconds = timeout_seconds
        self.max_retries = min(int(max_retries or 0), 2)
        self.session = session or requests

    @property
    def parent_type(self) -> str:
        return "data_source" if self.data_source_id else "page"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        attempts = 0
        while True:
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 0) or 0)
                try:
                    data = response.json()
                except ValueError:
                    data = {"text": getattr(response, "text", "")}
                if 200 <= status_code < 300:
                    return {"success": True, "status_code": status_code, "data": json_safe(data), "attempts": attempts + 1}
                retryable = status_code in TRANSIENT_STATUS_CODES
                if status_code in NON_RETRY_STATUS_CODES or not retryable or attempts >= self.max_retries:
                    return {
                        "success": False,
                        "status_code": status_code,
                        "data": json_safe(data),
                        "attempts": attempts + 1,
                        "error": _error("api_error", f"Notion API returned HTTP {status_code}.", retryable=retryable),
                    }
            except requests.exceptions.Timeout as exc:
                if attempts >= self.max_retries:
                    return {"success": False, "attempts": attempts + 1, "error": _error("timeout", str(exc), retryable=True)}
            except requests.exceptions.RequestException as exc:
                return {"success": False, "attempts": attempts + 1, "error": _error("api_error", str(exc), retryable=False)}
            attempts += 1

    def create_page(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        if self.parent_type == "data_source":
            payload = {"parent": {"database_id": self.data_source_id}, "properties": properties}
        else:
            payload = {
                "parent": {"page_id": self.parent_page_id},
                "properties": {"title": properties.get("title") or _rich_text("Untitled")},
            }
        return self._request("POST", f"{NOTION_BASE_URL}/pages", payload)

    def append_blocks(self, block_id: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for start in range(0, len(blocks), MAX_NOTION_CHILDREN_PER_APPEND):
            chunk = blocks[start : start + MAX_NOTION_CHILDREN_PER_APPEND]
            result = self._request(
                "PATCH",
                f"{NOTION_BASE_URL}/blocks/{block_id}/children",
                {"children": chunk},
            )
            results.append(result)
            if not result.get("success"):
                return {"success": False, "results": results, "error": result.get("error")}
        return {"success": True, "results": results}


def export_article_to_notion(
    article: Dict[str, Any],
    article_sources: Iterable[Dict[str, Any]],
    notion_client: Optional[NotionClient],
    dry_run: bool = True,
) -> Dict[str, Any]:
    article = json_safe(article or {})
    article_sources = json_safe(list(article_sources or []))
    validation = validate_article_exportable(article, article_sources)
    parent_type = getattr(notion_client, "parent_type", "data_source") if notion_client else "data_source"
    properties = build_notion_page_properties(article, article_sources, parent_type=parent_type)
    blocks = build_notion_blocks(article, article_sources)
    request_summary = _request_summary(parent_type, properties, blocks)
    base = {
        "article_id": article.get("id"),
        "dry_run": bool(dry_run),
        "exportable": bool(validation.get("exportable")),
        "validation": validation,
        "request_summary": request_summary,
        "notion": {
            "would_create_page": True,
            "would_append_blocks": True,
            "page_id": None,
            "url": None,
        },
        "summary": {
            "would_write_export_record": False,
            "would_publish": False,
        },
        "errors": [],
    }
    if not validation.get("exportable"):
        errors = validation.get("blockers") or []
        base["success"] = False
        base["errors"] = errors
        base["summary"]["export_record_status"] = "skipped"
        return json_safe(base)
    if dry_run:
        base["success"] = True
        return json_safe(base)
    if notion_client is None:
        base["success"] = False
        base["errors"] = [_error("config_error", "Notion client is required for export.")]
        base["summary"]["export_record_status"] = "failed"
        return json_safe(base)

    page_result = notion_client.create_page(properties)
    if not page_result.get("success"):
        base["success"] = False
        base["errors"] = [page_result.get("error") or _error("api_error", "Failed to create Notion page.")]
        base["summary"]["export_record_status"] = "failed"
        base["response_summary"] = _response_summary(page_result.get("data") or {})
        return json_safe(base)
    page_data = page_result.get("data") or {}
    page_id = page_data.get("id")
    append_result = notion_client.append_blocks(page_id, blocks)
    if not append_result.get("success"):
        base["success"] = False
        base["errors"] = [append_result.get("error") or _error("api_error", "Failed to append Notion blocks.")]
        base["summary"]["export_record_status"] = "failed"
        base["notion"].update({"page_id": page_id, "url": page_data.get("url")})
        base["response_summary"] = _response_summary(page_data)
        return json_safe(base)

    base["success"] = True
    base["notion"].update({"page_id": page_id, "url": page_data.get("url")})
    base["summary"].update({"export_record_status": "exported"})
    base["response_summary"] = _response_summary(page_data)
    return json_safe(base)


def save_article_export_record_to_postgres(
    dsn: str,
    export_result: Dict[str, Any],
    dry_run: bool = True,
) -> Dict[str, Any]:
    export_result = json_safe(export_result or {})
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "inserted_count": 0,
            "export_id": None,
            "errors": [],
        }
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    status = (export_result.get("summary") or {}).get("export_record_status") or ("exported" if export_result.get("success") else "failed")
    if status not in {"exported", "failed", "skipped", "dry_run"}:
        status = "failed"
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO article_exports (
                        article_id, target, target_id, target_url, status,
                        request_json, response_json, error_json, exported_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'exported' THEN NOW() ELSE NULL END)
                    RETURNING id
                    """,
                    (
                        export_result.get("article_id"),
                        "notion",
                        (export_result.get("notion") or {}).get("page_id"),
                        (export_result.get("notion") or {}).get("url"),
                        status,
                        Jsonb(export_result.get("request_summary") or {}),
                        Jsonb(export_result.get("response_summary") or {}),
                        Jsonb({"errors": export_result.get("errors") or []}),
                        status,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        export_id = row[0] if row and not isinstance(row, dict) else row.get("id") if row else None
        return {"success": True, "dry_run": False, "inserted_count": 1, "export_id": export_id, "status": status, "errors": []}
    except Exception as exc:
        return {"success": False, "dry_run": False, "inserted_count": 0, "export_id": None, "status": "failed", "errors": [_error("db_error", str(exc))]}


def build_notion_client_from_env(require_api_key: bool = True) -> Dict[str, Any]:
    config = load_notion_config(require_api_key=require_api_key)
    if not config.get("success"):
        return {"success": False, "config": config, "client": None, "errors": config.get("errors") or []}
    from notion_config import get_notion_api_key

    parent = get_notion_parent()
    client = NotionClient(
        get_notion_api_key(),
        data_source_id=parent.get("id") if parent.get("type") == "data_source" else None,
        parent_page_id=parent.get("id") if parent.get("type") == "page" else None,
        timeout_seconds=int(config.get("timeout_seconds") or 60),
        max_retries=int(config.get("max_retries") or 2),
    )
    return {"success": True, "config": config, "client": client, "errors": []}
