import os

import pytest

from llm_article_drafts import generate_llm_article_draft_candidate
from llm_gateway import LLMGateway
from llm_providers.openrouter import OpenRouterProvider


@pytest.mark.live_llm
def test_openrouter_live_llm_article_draft_candidate_dry_run_only():
    if not os.getenv("OPENROUTER_API_KEY") or not os.getenv("OPENROUTER_DEFAULT_MODEL"):
        pytest.skip("OPENROUTER_API_KEY and OPENROUTER_DEFAULT_MODEL are required for live LLM draft tests")

    topic = {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "daily_usdidr_update",
        "title": "USD/IDR Hari Ini",
        "status": "candidate",
        "reason_json": {"source_news_ids": [10]},
        "source_news_ids": [10],
    }
    source_bundle = {
        "topic_id": 1,
        "topic_type": "daily_usdidr_update",
        "symbol": "USDIDR",
        "source_news_ids": [10],
        "sources": [
            {
                "news_id": 10,
                "title": "Rupiah dan Dolar AS menjadi perhatian pasar",
                "summary": "Sumber berita tersimpan mencatat pasar mencermati Rupiah dan Dolar AS.",
                "url": "https://example.com/source-10",
                "source": "Example",
                "published_at": None,
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
    }

    result = generate_llm_article_draft_candidate(
        topic,
        source_bundle,
        LLMGateway(provider=OpenRouterProvider()),
        model_config={"max_retries": 0, "timeout_seconds": 30},
    )

    assert result["success"] is True
    assert result["draft_candidate"]["status"] == "pending_review"
    assert result["draft_candidate"]["published_at"] is None
    assert result["summary"]["would_write_db"] is False
    assert result["summary"]["would_publish"] is False
