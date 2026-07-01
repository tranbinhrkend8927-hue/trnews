from __future__ import annotations

import os
from typing import Optional

import requests
from pydantic import BaseModel, Field


NOTION_VERSION = "2025-09-03"
NOTION_BASE_URL = "https://api.notion.com/v1"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class NotionAPIError(BaseModel):
    type: str
    message: str
    status_code: Optional[int] = None
    retryable: bool = False
    raw: dict = Field(default_factory=dict)


class NotionAPIResult(BaseModel):
    success: bool
    data: dict | None = None
    error: NotionAPIError | None = None


class NotionClient:
    def __init__(
        self,
        api_key: str | None = None,
        notion_version: str | None = None,
        timeout_seconds: int = 30,
        session=None,
    ):
        self.api_key = api_key if api_key is not None else _env_value("NOTION_API_KEY")
        self.notion_version = notion_version or _env_value("NOTION_VERSION") or NOTION_VERSION
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def create_page(self, *, parent: dict, properties: dict) -> NotionAPIResult:
        return self._request(
            "post",
            f"{NOTION_BASE_URL}/pages",
            json={"parent": parent, "properties": properties},
        )

    def append_blocks(self, *, block_id: str, children: list[dict]) -> NotionAPIResult:
        return self._request(
            "patch",
            f"{NOTION_BASE_URL}/blocks/{block_id}/children",
            json={"children": children},
        )

    def query_data_source(
        self,
        *,
        data_source_id: str,
        filter: dict | None = None,
        sorts: list[dict] | None = None,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> NotionAPIResult:
        payload = {"page_size": page_size}
        if filter is not None:
            payload["filter"] = filter
        if sorts is not None:
            payload["sorts"] = sorts
        if start_cursor:
            payload["start_cursor"] = start_cursor
        return self._request(
            "post",
            f"{NOTION_BASE_URL}/data_sources/{data_source_id}/query",
            json=payload,
        )

    def update_page_properties(self, *, page_id: str, properties: dict) -> NotionAPIResult:
        return self._request(
            "patch",
            f"{NOTION_BASE_URL}/pages/{page_id}",
            json={"properties": properties},
        )

    def _request(self, method: str, url: str, *, json: dict) -> NotionAPIResult:
        if not self.api_key:
            return NotionAPIResult(
                success=False,
                error=NotionAPIError(
                    type="missing_notion_api_key",
                    message="NOTION_API_KEY is required for Notion API calls.",
                    retryable=False,
                ),
            )
        try:
            response = getattr(self.session, method)(
                url,
                headers=self._headers(),
                json=json,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            return NotionAPIResult(
                success=False,
                error=NotionAPIError(type="notion_request_exception", message=str(exc), retryable=True),
            )

        try:
            data = response.json()
        except Exception as exc:
            return NotionAPIResult(
                success=False,
                error=NotionAPIError(
                    type="notion_response_json_error",
                    message=str(exc),
                    status_code=getattr(response, "status_code", None),
                    retryable=bool(getattr(response, "status_code", 0) in RETRYABLE_STATUS_CODES),
                    raw={"text": getattr(response, "text", "")},
                ),
            )

        status_code = int(getattr(response, "status_code", 0) or 0)
        if 200 <= status_code < 300:
            return NotionAPIResult(success=True, data=data)
        return NotionAPIResult(
            success=False,
            data=data if isinstance(data, dict) else None,
            error=NotionAPIError(
                type="notion_api_error",
                message=str((data or {}).get("message") or f"Notion API returned HTTP {status_code}"),
                status_code=status_code,
                retryable=status_code in RETRYABLE_STATUS_CODES,
                raw=data if isinstance(data, dict) else {"value": data},
            ),
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }


def chunk_blocks(blocks: list[dict], chunk_size: int = 100) -> list[list[dict]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if not blocks:
        return []
    return [blocks[index : index + chunk_size] for index in range(0, len(blocks), chunk_size)]


def _env_value(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        from src.config.loader import load_local_env
    except Exception:
        return ""
    return str(load_local_env().get(name) or "")
