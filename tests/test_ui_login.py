from __future__ import annotations

import asyncio

import pytest
from yarl import URL

import ui.login as ui_login
from fakes import FakeTwitch


def output_texts(gui) -> list[str]:
    return [line.partition(": ")[2] for line in gui.output._text.get("1.0", "end-1c").splitlines()]


def test_the_line_with_the_login_code_is_in_the_language_of_the_app(window, monkeypatch, other_language):
    monkeypatch.setattr(ui_login, "_", other_language({"gui": {"login": {"enter_code": "Kod: {code}"}}}))
    opened: list[URL] = []
    monkeypatch.setattr(ui_login, "webopen", opened.append)
    gui = window(FakeTwitch())

    async def scenario() -> None:
        # the line is printed before the wait that comes before the browser opens
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gui.login.ask_enter_code(URL("https://www.twitch.tv/activate"), "AB12"), 0.1)

    asyncio.run(scenario())

    assert output_texts(gui)[-1] == "Kod: AB12"
    assert opened == []


def test_the_browser_button_ends_the_wait_with_used_browser_set(window):
    gui = window(FakeTwitch())

    async def scenario() -> tuple[str | None, bool]:
        task = asyncio.ensure_future(gui.login.ask_login())
        await asyncio.sleep(0)
        gui.login._browser_button.invoke()
        token = await asyncio.wait_for(task, 1)
        return token, gui.login.used_browser

    token, used_browser = asyncio.run(scenario())

    assert token is None
    assert used_browser is True
