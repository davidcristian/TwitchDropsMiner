from __future__ import annotations

import asyncio
import tkinter as tk

from fakes import FakeTwitch
import gui as gui_module


def test_the_window_leaves_color_fonts_out_before_tk_starts_when_libxft_is_older_than_2_3_5(window, monkeypatch):
    events: list[str] = []

    class OldXft:
        def xft_version(self) -> int:
            return 20304

        def use_fontconfig_rules(self, rules: bytes) -> bool:
            events.append("rules")
            return True

    class RecordedTk(tk.Tk):
        def __init__(self, *args, **kwargs) -> None:
            events.append("Tk")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gui_module, "LoadedFontLibraries", OldXft)
    monkeypatch.setattr(gui_module, "Tk", RecordedTk)
    window(FakeTwitch())

    assert events == ["rules", "Tk"]


def test_a_cancelled_caller_cancels_the_request_it_waits_for(window):
    gui = window(FakeTwitch())

    async def scenario():
        started = asyncio.Event()

        async def request():
            started.set()
            await asyncio.sleep(3600)

        caller = asyncio.create_task(gui.coro_unless_closed(request()))
        await started.wait()
        caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
        # a cancelled task ends on a later turn of the event loop
        for _turn in range(3):
            await asyncio.sleep(0)
        others = asyncio.all_tasks() - {asyncio.current_task()}
        return sorted(task.get_coro().__qualname__ for task in others)

    assert asyncio.run(scenario()) == []
