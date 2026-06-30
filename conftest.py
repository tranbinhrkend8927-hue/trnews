import os

import pytest


def pytest_collection_modifyitems(config, items):
    skip_live_network = pytest.mark.skip(
        reason="set RUN_LIVE_NETWORK=1 to run live network tests"
    )
    skip_live_llm = pytest.mark.skip(
        reason="set RUN_LLM_LIVE=1 to run live LLM tests"
    )
    skip_live_notion = pytest.mark.skip(
        reason="set RUN_NOTION_LIVE=1 to run live Notion tests"
    )
    for item in items:
        if "live_network" in item.keywords and os.getenv("RUN_LIVE_NETWORK") != "1":
            item.add_marker(skip_live_network)
        if "live_llm" in item.keywords and os.getenv("RUN_LLM_LIVE") != "1":
            item.add_marker(skip_live_llm)
        if "live_notion" in item.keywords and os.getenv("RUN_NOTION_LIVE") != "1":
            item.add_marker(skip_live_notion)
