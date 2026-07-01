from __future__ import annotations

from pydantic import BaseModel, Field

from src.notion.client import NotionClient, chunk_blocks
from src.notion.mapper import NotionBlockBuilder, NotionPropertyMapper
from src.notion.target_resolver import build_notion_parent_payload


class NotionExportPayload(BaseModel):
    target: dict
    parent: dict
    properties: dict
    blocks: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)


class NotionExportResult(BaseModel):
    success: bool
    dry_run: bool = True
    payload: NotionExportPayload | None = None
    page_id: str | None = None
    url: str | None = None
    error: dict | None = None
    metadata: dict = Field(default_factory=dict)


class NotionDryRunExporter:
    def __init__(self, target_resolver, property_mapper=None, block_builder=None):
        self.target_resolver = target_resolver
        self.property_mapper = property_mapper or NotionPropertyMapper()
        self.block_builder = block_builder or NotionBlockBuilder()

    def build_payload(
        self,
        *,
        target_name: str,
        article,
        market,
        language_profile,
        source_bundle,
        validation: dict | None = None,
        llm: dict | None = None,
        pipeline_run_id: str | None = None,
        content_job_key: str | None = None,
        source_bundle_hash: str | None = None,
        append_update_note: bool = False,
    ) -> NotionExportResult:
        target = self.target_resolver.resolve(target_name)
        warnings = list(target.warnings or [])
        if target.parent_id is None:
            warnings.append({"type": "missing_notion_parent_id", "target": target.name})
        payload = NotionExportPayload(
            target=target.model_dump() if hasattr(target, "model_dump") else target.dict(),
            parent=build_notion_parent_payload(target),
            properties=self.property_mapper.build_properties(
                article=article,
                market=market,
                language_profile=language_profile,
                source_bundle=source_bundle,
                validation=validation,
                llm=llm,
                pipeline_run_id=pipeline_run_id,
                content_job_key=content_job_key,
                source_bundle_hash=source_bundle_hash,
                target=target,
            ),
            blocks=self.block_builder.build_blocks(
                article=article,
                source_bundle=source_bundle,
                validation=validation,
                llm=llm,
            ),
            warnings=warnings,
        )
        return NotionExportResult(success=True, dry_run=True, payload=payload)


class NotionRealExporter:
    def __init__(
        self,
        target_resolver,
        notion_client=None,
        property_mapper=None,
        block_builder=None,
    ):
        self.dry_run_exporter = NotionDryRunExporter(
            target_resolver,
            property_mapper=property_mapper,
            block_builder=block_builder,
        )
        self.notion_client = notion_client or NotionClient()

    def export(
        self,
        *,
        target_name: str,
        article,
        market,
        language_profile,
        source_bundle,
        validation: dict | None = None,
        llm: dict | None = None,
        pipeline_run_id: str | None = None,
        content_job_key: str | None = None,
        source_bundle_hash: str | None = None,
        append_update_note: bool = False,
    ) -> NotionExportResult:
        preview = self.dry_run_exporter.build_payload(
            target_name=target_name,
            article=article,
            market=market,
            language_profile=language_profile,
            source_bundle=source_bundle,
            validation=validation,
            llm=llm,
            pipeline_run_id=pipeline_run_id,
            content_job_key=content_job_key,
            source_bundle_hash=source_bundle_hash,
        )
        payload = preview.payload
        if payload is None:
            return NotionExportResult(success=False, dry_run=False, error={"type": "payload_build_failed"})
        if not any(value for value in payload.parent.values()):
            return NotionExportResult(
                success=False,
                dry_run=False,
                payload=payload,
                error={"type": "missing_notion_parent_id", "message": "Notion parent id is required for export."},
            )

        create_result = self.notion_client.create_page(parent=payload.parent, properties=payload.properties)
        if not create_result.success:
            return NotionExportResult(
                success=False,
                dry_run=False,
                payload=payload,
                error=_api_error_dict(create_result.error),
            )

        page_data = create_result.data or {}
        page_id = page_data.get("id")
        url = page_data.get("url")
        for block_chunk in chunk_blocks(payload.blocks, chunk_size=100):
            append_result = self.notion_client.append_blocks(block_id=page_id, children=block_chunk)
            if not append_result.success:
                return NotionExportResult(
                    success=False,
                    dry_run=False,
                    payload=payload,
                    page_id=page_id,
                    url=url,
                    error=_api_error_dict(append_result.error),
                )

        return NotionExportResult(
            success=True,
            dry_run=False,
            payload=payload,
            page_id=page_id,
            url=url,
            metadata={"action": "created"},
        )


class NotionUpsertExporter:
    def __init__(
        self,
        target_resolver,
        notion_client=None,
        property_mapper=None,
        block_builder=None,
    ):
        self.dry_run_exporter = NotionDryRunExporter(
            target_resolver,
            property_mapper=property_mapper,
            block_builder=block_builder,
        )
        self.notion_client = notion_client or NotionClient()

    def export(
        self,
        *,
        target_name: str,
        article,
        market,
        language_profile,
        source_bundle,
        validation: dict | None = None,
        llm: dict | None = None,
        pipeline_run_id: str | None = None,
        content_job_key: str | None = None,
        source_bundle_hash: str | None = None,
        append_update_note: bool = False,
    ) -> NotionExportResult:
        if not content_job_key:
            return NotionExportResult(success=False, dry_run=False, error={"type": "missing_content_job_key"})
        preview = self.dry_run_exporter.build_payload(
            target_name=target_name,
            article=article,
            market=market,
            language_profile=language_profile,
            source_bundle=source_bundle,
            validation=validation,
            llm=llm,
            pipeline_run_id=pipeline_run_id,
            content_job_key=content_job_key,
            source_bundle_hash=source_bundle_hash,
        )
        payload = preview.payload
        if payload is None:
            return NotionExportResult(success=False, dry_run=False, error={"type": "payload_build_failed"})
        if not any(value for value in payload.parent.values()):
            return NotionExportResult(success=False, dry_run=False, payload=payload, error={"type": "missing_notion_parent_id"})
        if payload.target.get("parent_type") != "data_source":
            return NotionExportResult(success=False, dry_run=False, payload=payload, error={"type": "upsert_requires_data_source_parent"})

        data_source_id = payload.parent.get("data_source_id")
        query_result = self.notion_client.query_data_source(
            data_source_id=data_source_id,
            filter=build_content_job_key_filter(content_job_key),
            page_size=10,
        )
        if not query_result.success:
            return NotionExportResult(
                success=False,
                dry_run=False,
                payload=payload,
                error={"type": "notion_query_failed", "raw": _api_error_dict(query_result.error)},
            )

        existing_page = extract_first_page_from_query_result(query_result.data or {})
        if existing_page is None:
            return _create_from_payload(self.notion_client, payload, metadata={"action": "created"})

        page_id = existing_page.get("id")
        url = existing_page.get("url")
        update_result = self.notion_client.update_page_properties(page_id=page_id, properties=payload.properties)
        if not update_result.success:
            return NotionExportResult(
                success=False,
                dry_run=False,
                payload=payload,
                page_id=page_id,
                url=url,
                error=_api_error_dict(update_result.error),
                metadata={"action": "updated"},
            )
        if append_update_note:
            note = _update_note_block(pipeline_run_id=pipeline_run_id, content_job_key=content_job_key)
            append_result = self.notion_client.append_blocks(block_id=page_id, children=[note])
            if not append_result.success:
                return NotionExportResult(
                    success=False,
                    dry_run=False,
                    payload=payload,
                    page_id=page_id,
                    url=url,
                    error=_api_error_dict(append_result.error),
                    metadata={"action": "updated"},
                )
        return NotionExportResult(
            success=True,
            dry_run=False,
            payload=payload,
            page_id=page_id,
            url=url,
            metadata={"action": "updated"},
        )


def _api_error_dict(error) -> dict:
    if error is None:
        return {"type": "notion_api_error", "message": "Unknown Notion API error."}
    if hasattr(error, "model_dump"):
        return error.model_dump()
    if hasattr(error, "dict"):
        return error.dict()
    return dict(error)


def build_content_job_key_filter(content_job_key: str, property_name: str = "Content Job Key") -> dict:
    return {"property": property_name, "rich_text": {"equals": content_job_key}}


def extract_first_page_from_query_result(result_data: dict) -> dict | None:
    try:
        results = result_data.get("results") or []
    except AttributeError:
        return None
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return first if isinstance(first, dict) else None


def _create_from_payload(notion_client, payload: NotionExportPayload, *, metadata: dict) -> NotionExportResult:
    create_result = notion_client.create_page(parent=payload.parent, properties=payload.properties)
    if not create_result.success:
        return NotionExportResult(success=False, dry_run=False, payload=payload, error=_api_error_dict(create_result.error), metadata=metadata)
    page_data = create_result.data or {}
    page_id = page_data.get("id")
    url = page_data.get("url")
    for block_chunk in chunk_blocks(payload.blocks, chunk_size=100):
        append_result = notion_client.append_blocks(block_id=page_id, children=block_chunk)
        if not append_result.success:
            return NotionExportResult(
                success=False,
                dry_run=False,
                payload=payload,
                page_id=page_id,
                url=url,
                error=_api_error_dict(append_result.error),
                metadata=metadata,
            )
    return NotionExportResult(success=True, dry_run=False, payload=payload, page_id=page_id, url=url, metadata=metadata)


def _update_note_block(*, pipeline_run_id: str | None, content_job_key: str) -> dict:
    text = f"Updated existing draft. pipeline_run_id={pipeline_run_id or ''} content_job_key={content_job_key}"
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": text[:1800]}}]}}
