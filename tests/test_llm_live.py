import os

import pytest

from news_pipeline.llm_gateway import LLMGateway
from news_pipeline.llm_providers.openrouter import OpenRouterProvider
from news_pipeline.llm_schemas import BASIC_JSON_SCHEMA


@pytest.mark.live_llm
def test_openrouter_live_minimal_json_output():
    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_DEFAULT_MODEL"):
        pytest.skip("LLM_API_KEY and LLM_DEFAULT_MODEL are required for live LLM tests")

    result = LLMGateway(provider=OpenRouterProvider()).generate_json(
        "live_minimal_json_test",
        [
            {"role": "system", "content": "Return only JSON that matches the schema."},
            {"role": "user", "content": "Return a short message saying ok."},
        ],
        BASIC_JSON_SCHEMA,
        config={"max_retries": 0, "timeout_seconds": 30},
    )

    assert result["success"] is True
    assert isinstance(result["output"]["message"], str)
