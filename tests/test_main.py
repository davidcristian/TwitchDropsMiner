from __future__ import annotations

import io
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest

from constants import FILE_FORMATTER
from main import Parser, log_file_handler

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


class FakeBoxes:
    """The dialogs of `tkinter.messagebox`, which record each box they show as its kind, title and text."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str, str]] = []

    def showinfo(self, title: str, message: str) -> None:
        self.shown.append(("info", title, message))

    def showerror(self, title: str, message: str) -> None:
        self.shown.append(("error", title, message))


def parse(*arguments: str) -> tuple[int | str | None, list[tuple[str, str, str]]]:
    """Parse the arguments, and return the exit status and the boxes shown."""
    boxes = FakeBoxes()
    parser = Parser("app", boxes=boxes, title="Twitch Drops Miner", error_title="Argument Parser Error")
    parser.add_argument("--version", action="version", version="v1.0")
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(list(arguments))
    return exit_info.value.code, boxes.shown


def test_the_version_shows_in_an_information_box_with_the_app_name_as_its_title():
    assert parse("--version") == (0, [("info", "Twitch Drops Miner", "v1.0\n")])


def test_the_help_shows_in_an_information_box_with_the_app_name_as_its_title():
    status, shown = parse("--help")

    assert status == 0
    assert [(kind, title) for kind, title, text in shown] == [("info", "Twitch Drops Miner")]
    assert shown[0][2].startswith("usage: app [-h] [--version]\n")


def test_an_unknown_flag_shows_the_usage_and_the_error_in_an_error_box():
    usage = "usage: app [-h] [--version]\n"
    error = "app: error: unrecognized arguments: --bogus\n"

    assert parse("--bogus") == (2, [("error", "Argument Parser Error", usage + error)])
