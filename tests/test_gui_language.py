from __future__ import annotations

import asyncio
import logging
from tkinter import Misc, ttk

import pytest
from yarl import URL

import gui as gui_module
from fakes import FakeTwitch
from translate import default_translation

ENGLISH_LABEL = default_translation["gui"]["settings"]["general"]["language"]


def output_texts(gui) -> list[str]:
    return [line.partition(": ")[2] for line in gui.output._text.get("1.0", "end-1c").splitlines()]


def label_texts(widget: Misc) -> list[str]:
    """Return the text of every label inside widget."""
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Label):
            texts.append(str(child.cget("text")))
        texts.extend(label_texts(child))
    return texts


def test_the_line_with_the_login_code_is_in_the_language_of_the_app(window, monkeypatch, other_language):
    monkeypatch.setattr(gui_module, "_", other_language({"gui": {"login": {"enter_code": "Kod: {code}"}}}))
    opened: list[URL] = []
    monkeypatch.setattr(gui_module, "webopen", opened.append)
    gui = window(FakeTwitch())

    async def scenario() -> None:
        # the line is printed before the wait that comes before the browser opens
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gui.login.ask_enter_code(URL("https://www.twitch.tv/activate"), "AB12"), 0.1)

    asyncio.run(scenario())

    assert output_texts(gui)[-1] == "Kod: AB12"
    assert opened == []


def test_the_logging_level_line_is_in_the_language_of_the_app(window, monkeypatch, caplog, other_language):
    monkeypatch.setattr(gui_module, "_", other_language({"status": {"logging_level": "Poziom: {level}"}}))
    caplog.set_level(logging.INFO, logger="TwitchDrops")

    gui = window(FakeTwitch())

    assert output_texts(gui) == ["Poziom: INFO"]


def test_a_translated_language_label_starts_with_the_english_word(window, monkeypatch, other_language):
    strings = {"gui": {"settings": {"general": {"language": "Sprache (Neustart erforderlich): "}}}}
    monkeypatch.setattr(gui_module, "_", other_language(strings))

    gui = window(FakeTwitch())

    assert "Language / Sprache (Neustart erforderlich): " in label_texts(gui._root)


@pytest.mark.parametrize("strings", [None, {}])
def test_an_english_or_untranslated_language_label_shows_the_english_text_once(
    window, monkeypatch, other_language, strings
):
    if strings is not None:
        monkeypatch.setattr(gui_module, "_", other_language(strings))

    gui = window(FakeTwitch())

    labels = label_texts(gui._root)
    assert ENGLISH_LABEL in labels
    assert not any(text.startswith("Language / ") for text in labels)
