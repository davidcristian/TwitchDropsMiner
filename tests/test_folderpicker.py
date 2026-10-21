from __future__ import annotations

import asyncio
import multiprocessing
import time

import pytest

from fakedialog import FakeDialogs, chosen_in, failing, open_for_an_hour
from folderpicker import ChildDialog, FolderPicker, send_answer


def wait_for_answer(dialog: ChildDialog) -> str:
    deadline = time.monotonic() + 30
    while (folder := dialog.answer()) is None:
        assert time.monotonic() < deadline, "the child process sent no answer in 30 seconds"
        time.sleep(0.01)
    return folder


async def until(condition) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.01)


def test_the_child_sends_what_the_dialog_returns_for_its_title_and_start_folder_and_closes_the_pipe():
    receiver, sender = multiprocessing.Pipe(duplex=False)

    send_answer(sender, chosen_in, "Add", "/games")

    assert receiver.recv() == "/games/Add"
    with pytest.raises(EOFError):
        receiver.recv()


def test_the_child_closes_the_pipe_when_the_dialog_raises():
    receiver, sender = multiprocessing.Pipe(duplex=False)

    with pytest.raises(RuntimeError):
        send_answer(sender, failing, "Add", "/games")

    with pytest.raises(EOFError):
        receiver.recv()


def test_a_child_dialog_returns_the_folder_that_its_process_sends():
    dialog = ChildDialog("Add", "/games", ask=chosen_in)
    try:
        assert wait_for_answer(dialog) == "/games/Add"
    finally:
        dialog.close()


def test_a_child_dialog_whose_process_ends_without_an_answer_returns_no_folder():
    dialog = ChildDialog("Add", "/games", ask=failing)
    try:
        assert wait_for_answer(dialog) == ""
    finally:
        dialog.close()


def test_closing_an_open_child_dialog_ends_its_process():
    before = set(multiprocessing.active_children())
    dialog = ChildDialog("Add", "/games", ask=open_for_an_hour)
    children = set(multiprocessing.active_children()) - before
    answer = dialog.answer()

    dialog.close()

    assert answer is None
    assert len(children) == 1
    assert set(multiprocessing.active_children()) - before == set()


def test_choose_returns_the_folder_and_closes_the_dialog():
    dialogs = FakeDialogs()

    async def scenario() -> str:
        choice = asyncio.create_task(FolderPicker(dialogs).choose("Add"))
        await until(lambda: dialogs.opened)
        dialogs.opened[0].folder = "/games/Steam"
        return await choice

    assert asyncio.run(scenario()) == "/games/Steam"
    assert [(dialog.title, dialog.start, dialog.closed) for dialog in dialogs.opened] == [("Add", "", True)]


def test_other_tasks_run_while_a_dialog_is_open():
    dialogs = FakeDialogs()

    async def scenario() -> tuple[int, bool]:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        ticker = asyncio.create_task(tick())
        choice = asyncio.create_task(FolderPicker(dialogs).choose("Add"))
        await until(lambda: ticks >= 20)
        done_while_open = choice.done()
        dialogs.opened[0].folder = ""
        await choice
        ticker.cancel()
        return ticks, done_while_open

    ticks, done_while_open = asyncio.run(scenario())
    assert ticks >= 20
    assert not done_while_open


def test_each_dialog_opens_in_the_folder_that_the_last_one_returned():
    dialogs = FakeDialogs()
    picker = FolderPicker(dialogs)

    async def choose(folder: str) -> str:
        choice = asyncio.create_task(picker.choose("Add"))
        await until(lambda: dialogs.opened and not dialogs.opened[-1].closed and dialogs.opened[-1].folder is None)
        dialogs.opened[-1].folder = folder
        return await choice

    async def scenario() -> list[str]:
        return [await choose(folder) for folder in ("/games/Steam", "", "/games/Epic", "/games/GOG")]

    assert asyncio.run(scenario()) == ["/games/Steam", "", "/games/Epic", "/games/GOG"]
    # Cancel leaves the start folder of the next dialog as it was
    assert [dialog.start for dialog in dialogs.opened] == ["", "/games/Steam", "/games/Steam", "/games/Epic"]


def test_a_cancelled_choose_closes_its_open_dialog():
    dialogs = FakeDialogs()

    async def scenario() -> None:
        choice = asyncio.create_task(FolderPicker(dialogs).choose("Add"))
        await until(lambda: dialogs.opened)
        choice.cancel()
        with pytest.raises(asyncio.CancelledError):
            await choice

    asyncio.run(scenario())
    assert [dialog.closed for dialog in dialogs.opened] == [True]
