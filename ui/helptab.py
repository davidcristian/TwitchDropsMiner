"""`HelpTab`, the Help tab: the links, the help text and the Invalidate button."""
from __future__ import annotations

import logging
from tkinter import ttk
from typing import TYPE_CHECKING

from translate import _
from utils import start_task, task_wrapper
from constants import State

from .widgets import LinkLabel

if TYPE_CHECKING:
    from gui import GUIManager


logger = logging.getLogger("TwitchDrops")


class HelpTab:
    WIDTH = 800

    def __init__(self, manager: GUIManager, master: ttk.Widget):
        self._twitch = manager._twitch
        master.rowconfigure(0, weight=1)
        master.columnconfigure(0, weight=1)
        # use a frame to center the content within the tab
        center_frame = ttk.Frame(master)
        center_frame.grid(column=0, row=0)
        # use a frame for the bottom row specifically
        bottom_frame = ttk.Frame(master)
        bottom_frame.grid(column=0, row=1, sticky="nsew")
        irow = 0
        # About
        about = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "help", "about", "name")
        )
        about.grid(column=0, row=(irow := irow + 1), sticky="nsew", padx=2)
        about.columnconfigure(2, weight=1)
        # About - repo link
        ttk.Label(
            about, text=_("gui", "help", "about", "repository"), anchor="e"
        ).grid(column=0, row=0, sticky="nsew")
        LinkLabel(
            about,
            link="https://github.com/davidcristian/TwitchDropsMiner",
            text="https://github.com/davidcristian/TwitchDropsMiner",
        ).grid(column=1, row=0, sticky="nsew")
        # About - original project
        ttk.Label(
            about, text=_("gui", "help", "about", "based_on"), anchor="e"
        ).grid(column=0, row=1, sticky="nsew")
        LinkLabel(
            about,
            link="https://github.com/DevilXD/TwitchDropsMiner",
            text=_("gui", "help", "about", "based_on_text"),
        ).grid(column=1, row=1, sticky="nsew")
        # Useful links
        links = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "help", "links", "name")
        )
        links.grid(column=0, row=(irow := irow + 1), sticky="nsew", padx=2)
        LinkLabel(
            links,
            link="https://www.twitch.tv/drops/inventory",
            text=_("gui", "help", "links", "inventory"),
        ).grid(column=0, row=0, sticky="nsew")
        LinkLabel(
            links,
            link="https://www.twitch.tv/drops/campaigns",
            text=_("gui", "help", "links", "campaigns"),
        ).grid(column=0, row=1, sticky="nsew")
        # How It Works
        howitworks = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "help", "how_it_works")
        )
        howitworks.grid(column=0, row=(irow := irow + 1), sticky="nsew", padx=2)
        ttk.Label(
            howitworks, text=_("gui", "help", "how_it_works_text"), wraplength=self.WIDTH
        ).grid(sticky="nsew")
        getstarted = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "help", "getting_started")
        )
        getstarted.grid(column=0, row=(irow := irow + 1), sticky="nsew", padx=2)
        ttk.Label(
            getstarted, text=_("gui", "help", "getting_started_text"), wraplength=self.WIDTH
        ).grid(sticky="nsew")

        # Invalidate button
        invalidate_frame = ttk.Frame(bottom_frame)
        bottom_frame.columnconfigure(0, weight=1)  # center within the column
        invalidate_frame.grid(column=0, row=0, sticky="nse")
        ttk.Label(
            invalidate_frame, text=_("gui", "help", "invalidate", "text")
        ).grid(column=0, row=0)
        self._invalidate_button: ttk.Button = ttk.Button(
            invalidate_frame,
            text=_("gui", "help", "invalidate", "button"),
            command=self.invalidate_token,
            state="disabled",
        )
        self._invalidate_button.grid(column=1, row=0)

    def invalidate_token(self) -> None:
        # sync to async bridge
        start_task(task_wrapper(self._invalidate_token)())

    async def _invalidate_token(self) -> None:
        auth_state = await self._twitch.get_auth()
        async with self._twitch.request(
            "POST",
            "https://id.twitch.tv/oauth2/revoke",
            data={
                "client_id": self._twitch._client_type.CLIENT_ID,
                "token": auth_state.access_token,
            }
        ) as response:
            if response.status == 200:
                auth_state.invalidate(delete_cookies=True)
            else:
                logger.error(f"Failed to invalidate the auth token: {response.status}")
        self._twitch.change_state(State.RESTART)
