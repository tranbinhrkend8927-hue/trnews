import json
import os
import subprocess
import sys
from pathlib import Path


def test_importing_library_modules_has_no_process_side_effects(tmp_path):
    (tmp_path / ".env").write_text("TV_IMPORT_SIDE_EFFECT_SHOULD_NOT_EXIST=1\n")
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import json
import logging
import os
import signal

root = logging.getLogger()
before = {
    "level": root.level,
    "handlers": len(root.handlers),
    "sigint": repr(signal.getsignal(signal.SIGINT)),
}

import tradingview_scraper.symbols.news
import tradingview_scraper.symbols.ideas
import tradingview_scraper.symbols.stream.stream_handler
import tradingview_scraper.symbols.stream.streamer
import tradingview_scraper.symbols.stream.price

after = {
    "level": root.level,
    "handlers": len(root.handlers),
    "sigint": repr(signal.getsignal(signal.SIGINT)),
}
print(json.dumps({
    "logger_unchanged": before["level"] == after["level"] and before["handlers"] == after["handlers"],
    "signal_unchanged": before["sigint"] == after["sigint"],
    "dotenv_loaded": "TV_IMPORT_SIDE_EFFECT_SHOULD_NOT_EXIST" in os.environ,
}))
"""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload == {
        "logger_unchanged": True,
        "signal_unchanged": True,
        "dotenv_loaded": False,
    }
