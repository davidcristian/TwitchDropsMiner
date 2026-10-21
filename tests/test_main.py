from __future__ import annotations

import io
import logging
import re
import subprocess
import sys
from pathlib import Path

from constants import FILE_FORMATTER
from main import log_file_handler

MAIN = Path(__file__).resolve().parent.parent / "main.py"
# Runs main.py as a script on a fake Python 3.9, which cannot install truststore and has no typing.ParamSpec
# for utils.py to import
OLD_PYTHON = """
import runpy
import sys
sys.version_info = (3, 9, 18, "final", 0)
sys.modules["truststore"] = None
sys.modules["utils"] = None
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def test_an_older_python_stops_with_the_version_message(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", OLD_PYTHON, str(MAIN)], capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 1
    assert result.stderr.splitlines()[-1] == "RuntimeError: Python 3.10 or higher is required"


def cp1252_by_default(encoding: str | None, stacklevel: int = 2) -> str:
    return "cp1252" if encoding is None else encoding


def test_the_log_file_keeps_korean_and_chinese_text_when_the_locale_code_page_is_cp1252(monkeypatch, tmp_path):
    # FileHandler gets the encoding of a file opened without one from io.text_encoding, and this one returns the
    # code page of a Western Windows
    monkeypatch.setattr(io, "text_encoding", cp1252_by_default)
    handler = log_file_handler(tmp_path / "log.txt", FILE_FORMATTER)
    record = logging.LogRecord("TwitchDrops", logging.WARNING, __file__, 1, "Watching 침착맨 and 中文频道", None, None)

    handler.handle(record)
    handler.close()

    line = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}:\tWARNING:\tWatching 침착맨 and 中文频道\n", line)
