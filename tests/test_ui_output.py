from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fakes import FakeTwitch
from gui import GUIManager


def output_texts(gui: GUIManager) -> list[str]:
    """Return the lines of the Output box without their time stamps."""
    return [line.partition(": ")[2] for line in gui.output._text.get("1.0", "end-1c").splitlines()]


def test_the_output_box_keeps_the_last_5000_lines(window):
    gui = window(FakeTwitch())
    for number in range(5003):
        gui.print(f"line {number}")

    lines = gui.output._text.get("1.0", "end-1c").splitlines()
    assert len(lines) == 5000
    assert [line.rpartition(": ")[2] for line in (lines[0], lines[-1])] == ["line 3", "line 5002"]


def test_a_record_logged_on_another_thread_reaches_the_output_box(window, caplog):
    gui = window(FakeTwitch())
    caplog.set_level(logging.DEBUG, logger="TwitchDrops")
    logger = logging.getLogger("TwitchDrops")

    async def scenario() -> None:
        gui.start()
        # Twitch.detect_games runs the game scan in a thread in this way, and gamelib logs at DEBUG there
        await asyncio.to_thread(logger.debug, "Game library: malformed manifest")
        # longer than the wait of GUIManager._poll between its passes, so it makes at least one more
        await asyncio.sleep(0.2)
        gui.stop()

    asyncio.run(scenario())

    assert output_texts(gui)[-1] == "DEBUG: Game library: malformed manifest"


def test_a_record_from_another_thread_is_shown_before_a_later_record_of_the_window_thread(window):
    gui = window(FakeTwitch())
    logger = logging.getLogger("TwitchDrops")
    with ThreadPoolExecutor(max_workers=1) as other:
        other.submit(logger.error, "first").result()
    logger.error("second")

    assert output_texts(gui)[-2:] == ["ERROR: first", "ERROR: second"]
