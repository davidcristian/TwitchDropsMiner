"""`LoginForm`, the panel of the Main tab that shows the login status and waits for a login or a token."""
from __future__ import annotations

import asyncio
from tkinter import ttk, StringVar
from typing import TYPE_CHECKING

from yarl import URL

from translate import _
from utils import webopen
from tokencheck import entered_token

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
        self._entered: str | None = None
        self._button = ttk.Button(
            frame, text=_("gui", "login", "button"), command=self._confirm.set, state="disabled"
        )
        self._button.grid(column=0, row=1, columnspan=2)
        ttk.Label(frame, text=_("gui", "login", "token")).grid(column=0, row=2)
        self._token = ttk.Entry(frame, width=12, show="*", state="disabled")
        self._token.grid(column=1, row=2, sticky="ew")
        self._token_button = ttk.Button(
            frame, text=_("gui", "login", "token_button"), command=self._use_token, state="disabled"
        )
        self._token_button.grid(column=0, row=3, columnspan=2, pady=(2, 0))
        self.update(_("gui", "login", "logged_out"), None)

    def _use_token(self) -> None:
        if token := entered_token(self._token.get()):
            self._entered = token
            self._token.delete(0, "end")
            self._confirm.set()

    async def wait_for_login_press(self) -> str | None:
        """Wait for a press of Login, which returns None, or of the token button with a token, which returns it."""
        self._confirm.clear()
        self._entered = None
        widgets = (self._button, self._token, self._token_button)
        try:
            for widget in widgets:
                widget.config(state="normal")
            await self._manager.coro_unless_closed(self._confirm.wait())
            return self._entered
        finally:
            for widget in widgets:
                widget.config(state="disabled")

    async def ask_login(self) -> str | None:
        """Ask the user to log in, and return the token they entered, or None when they press Login."""
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
