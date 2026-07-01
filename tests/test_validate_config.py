import json

from src.jobs.validate_config import main


def test_validate_config_cli_prints_success_json(capsys):
    exit_code = main([])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["errors"] == []
    assert isinstance(payload["warnings"], list)


def test_validate_config_cli_fails_for_missing_config_dir(capsys, tmp_path):
    exit_code = main(["--config-dir", str(tmp_path / "missing")])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"]
