from __future__ import annotations

import asyncio
import gc
import weakref

from utils import format_traceback, start_task


async def wait_for_a_future(futures: list[weakref.ref[asyncio.Future[str]]], results: list[str]) -> None:
    # nothing but this task references the future it waits for
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    futures.append(weakref.ref(future))
    results.append(await future)


def test_start_task_keeps_a_task_that_nothing_else_references_until_it_ends():
    futures: list[weakref.ref[asyncio.Future[str]]] = []
    results: list[str] = []

    async def scenario():
        start_task(wait_for_a_future(futures, results))
        await asyncio.sleep(0)
        gc.collect()
        future = futures[0]()
        if future is not None:
            future.set_result("done")
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert results == ["done"]


def test_start_task_drops_its_reference_once_the_task_ends():
    async def scenario():
        task = start_task(asyncio.sleep(0))
        ended = asyncio.Event()
        # done callbacks run in the order they were added, so the one of start_task has run when this one runs
        task.add_done_callback(lambda _task: ended.set())
        reference = weakref.ref(task)
        del task
        await ended.wait()
        gc.collect()
        return reference()

    assert asyncio.run(scenario()) is None


def raise_with_cause() -> None:
    try:
        raise KeyError("cause")
    except KeyError as cause:
        raise ValueError("boom") from cause


def test_format_traceback_returns_the_lines_of_a_raised_exception():
    try:
        raise_with_cause()
    except ValueError as exc:
        text = format_traceback(exc)

    assert text.startswith("Traceback (most recent call last):\n")
    assert "in raise_with_cause\n" in text
    assert "The above exception was the direct cause of the following exception" in text
    assert text.endswith("ValueError: boom\n")


def test_format_traceback_passes_its_keywords_to_the_traceback_module():
    try:
        raise_with_cause()
    except ValueError as exc:
        text = format_traceback(exc, chain=False)

    assert "KeyError" not in text
    assert text.endswith("ValueError: boom\n")


def test_format_traceback_of_an_exception_that_was_never_raised_is_its_last_line():
    assert format_traceback(ValueError("boom")) == "ValueError: boom\n"
