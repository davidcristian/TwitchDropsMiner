"""The mixin of `GUIManager` that runs Tk on the asyncio event loop and closes the window."""
from __future__ import annotations

import asyncio
import logging
import tkinter as tk
from collections import abc
from typing import Any, NoReturn, TYPE_CHECKING

from exceptions import ExitRequest
from utils import _T

if TYPE_CHECKING:
    from tkinter import Tk

    from twitch import Twitch
    from scrollarea import MinimumSize
    from .tray import TrayIcon
    from .progress import CampaignProgress
    from .output import _TKOutputHandler


class EventLoopMixin:
    """The methods of `GUIManager` that start and stop the poll of Tk events, and pass on a close request."""

    _twitch: Twitch
    _root: Tk
    _poll_task: asyncio.Task[NoReturn] | None
    _close_requested: asyncio.Event
    _handler: _TKOutputHandler
    _minimum: MinimumSize
    progress: CampaignProgress
    tray: TrayIcon

    @property
    def running(self) -> bool:
        return self._poll_task is not None

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    async def wait_until_closed(self):
        # wait until the user closes the window
        await self._close_requested.wait()

    async def coro_unless_closed(self, coro: abc.Awaitable[_T]) -> _T:
        # In Python 3.11, we need to explicitly wrap awaitables
        tasks = [asyncio.ensure_future(coro), asyncio.ensure_future(self._close_requested.wait())]
        done: set[asyncio.Task[Any]]
        pending: set[asyncio.Task[Any]]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            # asyncio.wait does not cancel the tasks it waits for
            for task in tasks:
                task.cancel()
            raise
        for task in pending:
            task.cancel()
        if self._close_requested.is_set():
            raise ExitRequest()
        return await next(iter(done))

    def prevent_close(self):
        self._close_requested.clear()

    def start(self):
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll())
        # self.progress.start_timer()

    def stop(self):
        self.progress.stop_timer()
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll(self):
        """
        Processes pending Tk events every 0.05 seconds on the asyncio loop, in place of mainloop.
        """
        do_one_event = self._root.dooneevent
        # TKINTER_DONT_WAIT (1 << 1) tells Tcl to return immediately
        # if no events are ready in the queue.
        DONT_WAIT = 1 << 1

        while True:
            try:
                # Drain pending Tk events non-blockingly
                while do_one_event(DONT_WAIT):
                    pass
                self._handler.print_queued()
                self._minimum.follow()
            except tk.TclError:
                # Root window was destroyed
                break
            await asyncio.sleep(0.05)

        self._poll_task = None

    def close(self, *args) -> int:
        """
        Requests the GUI application to close.
        The window itself will be closed in the closing sequence later.
        """
        self._close_requested.set()
        # notify client we're supposed to close
        self._twitch.close()
        return 0

    def close_window(self):
        """
        Closes the window. Invalidates the logger.
        """
        self.tray.stop()
        logging.getLogger("TwitchDrops").removeHandler(self._handler)
        self._root.destroy()
