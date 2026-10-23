from __future__ import annotations

import asyncio
import gc
import logging
import re
import weakref
from datetime import datetime, timezone

import pytest

from exceptions import ExitRequest, ReloadRequest
from utils import (
    CHARS_ASCII,
    CHARS_HEX_LOWER,
    AwaitableValue,
    chunk,
    create_nonce,
    format_traceback,
    isonow,
    json_minify,
    start_task,
    task_wrapper,
    timestamp,
)


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


@pytest.mark.parametrize("items, length, expected", [
    (range(7), 3, [[0, 1, 2], [3, 4, 5], [6]]),
    ("abcd", 2, [["a", "b"], ["c", "d"]]),
    ((number for number in range(3)), 20, [[0, 1, 2]]),
    ([], 20, []),
])
def test_chunk_yields_lists_of_the_length_and_a_shorter_last_list(items, length, expected):
    assert list(chunk(items, length)) == expected


def test_chunk_of_length_zero_raises_value_error():
    with pytest.raises(ValueError):
        list(chunk([1], 0))


def test_json_minify_writes_no_spaces():
    text = json_minify({"type": "PING", "data": {"topics": ["a", "b"]}})

    assert text == '{"type":"PING","data":{"topics":["a","b"]}}'


def test_json_minify_writes_a_list_and_escapes_characters_outside_ascii():
    assert json_minify([{"name": "Pokémon"}]) == '[{"name":"Pok\\u00e9mon"}]'


@pytest.mark.parametrize("text, expected", [
    ("2026-10-23T12:34:56.789Z", datetime(2026, 10, 23, 12, 34, 56, 789000, tzinfo=timezone.utc)),
    ("2026-10-23T12:34:56Z", datetime(2026, 10, 23, 12, 34, 56, tzinfo=timezone.utc)),
])
def test_timestamp_reads_a_utc_time_with_or_without_fractions_of_a_second(text, expected):
    assert timestamp(text) == expected


@pytest.mark.parametrize("text", ["2026-10-23T12:34:56+02:00", "2026-10-23", ""])
def test_timestamp_of_another_format_raises_value_error(text):
    with pytest.raises(ValueError):
        timestamp(text)


def test_isonow_returns_the_current_utc_time_in_milliseconds_with_a_z():
    now = datetime.now(timezone.utc)
    # isonow cuts the time to milliseconds
    before = now.replace(microsecond=now.microsecond // 1000 * 1000)
    text = isonow()
    after = datetime.now(timezone.utc)

    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", text)
    assert before <= timestamp(text) <= after


@pytest.mark.parametrize("chars, length, pattern", [
    (CHARS_ASCII, 30, r"[A-Za-z0-9]{30}"),
    (CHARS_HEX_LOWER, 16, r"[0-9a-f]{16}"),
    (CHARS_ASCII, 0, r""),
])
def test_create_nonce_returns_length_characters_of_the_set(chars, length, pattern):
    assert re.fullmatch(pattern, create_nonce(chars, length))


def test_create_nonce_from_no_characters_raises_index_error():
    with pytest.raises(IndexError):
        create_nonce("", 1)


@pytest.mark.parametrize("request_type", [ExitRequest, ReloadRequest])
def test_task_wrapper_ends_the_task_without_an_error_on_an_exit_or_reload_request(request_type, caplog):
    @task_wrapper
    async def stopped() -> None:
        raise request_type()

    asyncio.run(stopped())

    assert caplog.records == []


def test_task_wrapper_logs_another_error_and_raises_it_again(caplog):
    @task_wrapper
    async def failing() -> None:
        raise KeyError("boom")

    with pytest.raises(KeyError):
        asyncio.run(failing())

    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (logging.ERROR, "Exception in failing task")
    ]
    assert caplog.records[0].exc_info is not None


@pytest.mark.parametrize("args", [(), (None,), (object(),)])
def test_a_critical_task_with_no_twitch_in_its_first_argument_raises_its_error_again(args):
    @task_wrapper(critical=True)
    async def failing(*args: object) -> None:
        raise KeyError("boom")

    with pytest.raises(KeyError):
        asyncio.run(failing(*args))

    assert failing.__name__ == "failing"


def test_an_awaitable_value_without_a_value_returns_the_default():
    value: AwaitableValue[int] = AwaitableValue()

    assert (value.has_value(), value.get_with_default(None)) == (False, None)


def test_get_waits_until_a_value_is_set():
    async def scenario():
        value: AwaitableValue[str] = AwaitableValue()
        getter = asyncio.ensure_future(value.get())
        await asyncio.sleep(0)
        waited = not getter.done()
        value.set("ready")
        return waited, await getter, value.has_value(), value.get_with_default("default")

    assert asyncio.run(scenario()) == (True, "ready", True, "ready")


def test_clear_makes_an_awaitable_value_wait_again():
    async def scenario():
        value: AwaitableValue[str] = AwaitableValue()
        value.set("old")
        value.clear()
        cleared = (value.has_value(), value.get_with_default("default"))
        getter = asyncio.ensure_future(value.get())
        await asyncio.sleep(0)
        waited = not getter.done()
        value.set("new")
        return cleared, waited, await getter

    assert asyncio.run(scenario()) == ((False, "default"), True, "new")
