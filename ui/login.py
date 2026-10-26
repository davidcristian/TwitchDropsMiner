"""`LoginForm`, the panel of the Main tab that shows the login status and waits for a login."""
from __future__ import annotations

import asyncio
from tkinter import ttk, StringVar
from typing import TYPE_CHECKING

from yarl import URL

from translate import _
from utils import webopen

if TYPE_CHECKING:
    from gui import GUIManager


class LoginForm:
    def __init__(self, manager: GUIManager, master: ttk.Widget):
        self._manager = manager
        self._var = StringVar(master)
        frame = ttk.LabelFrame(master, text=_("gui", "login", "name"), padding=(4, 0, 4, 4))
        frame.grid(column=1, row=1, sticky="nsew", padx=2)
        frame.columnconfigure(0, weight=2)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=_("gui", "login", "labels")).grid(column=0, row=0)
        ttk.Label(frame, textvariable=self._var, justify="center").grid(column=1, row=0)

        self._confirm = asyncio.Event()
        self._browser = False
        self._button = ttk.Button(
            frame, text=_("gui", "login", "button"), command=self._confirm.set, state="disabled"
        )
        self._button.grid(column=0, row=1, columnspan=2)
        self._browser_button = ttk.Button(
            frame, text=_("gui", "login", "browser_button"), command=self._use_browser, state="disabled"
        )
        self._browser_button.grid(column=0, row=2, columnspan=2, pady=(2, 0))
        self.update(_("gui", "login", "logged_out"), None)

    def _use_browser(self) -> None:
        self._browser = True
        self._confirm.set()

    @property
    def used_browser(self) -> bool:
        """Whether the last ask ended with a press of the browser login button."""
        return self._browser

    async def wait_for_login_press(self) -> None:
        """Wait for a press of the Login button or the browser login button."""
        self._confirm.clear()
        self._browser = False
        widgets = (self._button, self._browser_button)
        try:
            for widget in widgets:
                widget.config(state="normal")
            await self._manager.coro_unless_closed(self._confirm.wait())
        finally:
            for widget in widgets:
                widget.config(state="disabled")

    async def ask_login(self) -> None:
        """Ask the user to log in, and return when they press Login or the browser login button."""
        self.update(_("gui", "login", "required"), None)
        # ensure the window isn't hidden into tray when this runs
        self._manager.grab_attention(sound=False)
        self._manager.print(_("gui", "login", "request"))
        return await self.wait_for_login_press()

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        """Show the code to enter, then open the activation page in the browser."""
        self._manager.print(_("gui", "login", "enter_code").format(code=user_code))
        await asyncio.sleep(4)
        webopen(page_url)

    def update(self, status: str, user_id: int | None):
        if user_id is not None:
            user_str = str(user_id)
        else:
            user_str = "-"
        self._var.set(f"{status}\n{user_str}")
