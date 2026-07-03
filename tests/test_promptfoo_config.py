import json
from pathlib import Path


PROMPTFOO_CONFIG = Path("evals/promptfoo.yaml")
SAMPLE_DIR = Path("evals/samples/usd_idr")


def test_promptfoo_config_is_json_yaml_subset_and_opt_in():
    config = json.loads(PROMPTFOO_CONFIG.read_text(encoding="utf-8"))

    assert config["description"]
    assert config["prompts"] == ["{{article_brief}}"]
    assert config["providers"][0]["id"] == "openai:responses:{{env.LLM_DEFAULT_MODEL}}"
    assert config["providers"][0]["config"]["text"]["format"]["type"] == "json_object"
    assert len(config["tests"]) >= 3
    assert any(assertion["type"] == "llm-rubric" for assertion in config["defaultTest"]["assert"])


def test_promptfoo_tests_reference_existing_samples():
    config = json.loads(PROMPTFOO_CONFIG.read_text(encoding="utf-8"))

    for test_case in config["tests"]:
        sample_file = Path(test_case["metadata"]["sample_file"])
        assert sample_file.exists(), f"Missing sample file: {sample_file}"
        sample = json.loads(sample_file.read_text(encoding="utf-8"))
        assert sample["id"] == test_case["vars"]["sample_id"]


def test_promptfoo_samples_have_expected_contract():
    samples = sorted(SAMPLE_DIR.glob("*.json"))

    assert len(samples) >= 3
    for sample_path in samples:
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        assert sample["id"].startswith("usd_idr_")
        assert sample["market_id"] == "usd_idr_id"
        assert sample["language"] == "id"
        assert sample["source_bundle"]["sources"]
        assert "source_quality_report" in sample["source_bundle"]
        assert sample["expected"]["must_include_sections"]
        assert sample["expected"]["forbidden_phrases"]
        assert sample["expected"]["minimum_source_count"] >= 1


def test_promptfoo_eval_is_not_part_of_pytest_runtime():
    config = json.loads(PROMPTFOO_CONFIG.read_text(encoding="utf-8"))

    assert "promptfoo eval" not in json.dumps(config)
    assert Path("evals/README.md").read_text(encoding="utf-8").count("ENABLE_PROMPTFOO_EVALS=1") >= 1
