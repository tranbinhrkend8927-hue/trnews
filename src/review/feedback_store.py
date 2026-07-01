from __future__ import annotations

import json
from pathlib import Path

from src.review.feedback import ReviewFeedback


class JsonlReviewFeedbackStore:
    def __init__(self, path: str = ".runs/review_feedback.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, feedback: ReviewFeedback) -> None:
        payload = feedback.model_dump() if hasattr(feedback, "model_dump") else feedback.dict()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def list_feedback(self) -> list[ReviewFeedback]:
        if not self.path.exists():
            return []
        items: list[ReviewFeedback] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                items.append(ReviewFeedback(**json.loads(line)))
            except Exception:
                continue
        return items

    def filter_feedback(
        self,
        *,
        review_status: str | None = None,
        market_id: str | None = None,
        language: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        content_job_key: str | None = None,
        limit: int | None = None,
    ) -> list[ReviewFeedback]:
        items = self.list_feedback()
        if review_status is not None:
            items = [item for item in items if item.review_status == review_status]
        if market_id is not None:
            items = [item for item in items if item.market_id == market_id]
        if language is not None:
            items = [item for item in items if item.language == language]
        if model is not None:
            items = [item for item in items if item.model == model]
        if prompt_version is not None:
            items = [item for item in items if item.prompt_version == prompt_version]
        if content_job_key is not None:
            items = [item for item in items if item.content_job_key == content_job_key]
        return items[:limit] if limit is not None else items

    def latest_by_content_job_key(self, content_job_key: str) -> ReviewFeedback | None:
        matches = self.filter_feedback(content_job_key=content_job_key)
        return matches[-1] if matches else None

    def latest_by_notion_page_id(self, notion_page_id: str) -> ReviewFeedback | None:
        matches = [item for item in self.list_feedback() if item.notion_page_id == notion_page_id]
        return matches[-1] if matches else None
