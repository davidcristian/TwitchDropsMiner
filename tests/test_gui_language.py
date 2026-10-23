from __future__ import annotations

import logging

import gui as gui_module
from fakes import FakeTwitch


def output_texts(gui) -> list[str]:
    return [line.partition(": ")[2] for line in gui.output._text.get("1.0", "end-1c").splitlines()]


def test_the_logging_level_line_is_in_the_language_of_the_app(window, monkeypatch, caplog, other_language):
    monkeypatch.setattr(gui_module, "_", other_language({"status": {"logging_level": "Poziom: {level}"}}))
    caplog.set_level(logging.INFO, logger="TwitchDrops")

    gui = window(FakeTwitch())

    assert output_texts(gui) == ["Poziom: INFO"]
