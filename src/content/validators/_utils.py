from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.content.article_schema import ArticleDraft


def parse_article(article: ArticleDraft | dict[str, Any]) -> ArticleDraft:
    if isinstance(article, ArticleDraft):
        return article
    if hasattr(ArticleDraft, "model_validate"):
        return ArticleDraft.model_validate(article)
    return ArticleDraft.parse_obj(article)


def article_to_dict(article: ArticleDraft) -> dict[str, Any]:
    if hasattr(article, "model_dump"):
        return article.model_dump()
    return article.dict()


def pydantic_error_summary(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "field": ".".join(str(part) for part in error.get("loc", [])),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
