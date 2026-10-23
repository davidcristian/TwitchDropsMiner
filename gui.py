from __future__ import annotations

import os
import sys
import ctypes
import asyncio
import logging
import tkinter as tk
from pathlib import Path
from collections import abc
from tkinter.font import Font, nametofont
from functools import partial, cached_property
from datetime import datetime, timedelta, timezone
from tkinter import Tk, ttk, StringVar, IntVar
from typing import Any, TypedDict, NoReturn, TYPE_CHECKING

from yarl import URL
from PIL.ImageTk import PhotoImage
from PIL import Image as Image_module

if sys.platform == "win32":
    import win32api
    import win32con
    import win32gui

if sys.platform == "darwin":
    import AppKit

from translate import _, default_translation
from cache import ImageCache
from colorfonts import LoadedFontLibraries, skip_color_fonts
from autostart import AutostartEntry, autostart_command, autostart_entry, source_python
from gamelib import (
    GameMatch,
    MatchKind,
    any_match,
    match_rank,
    has_wildcard,
    matching_names,
    compile_pattern,
    compile_patterns,
)
from exceptions import MinerException, ExitRequest
from folderpicker import FolderPicker
from traybackend import hides_by_stopping, icon_class, import_pystray, load_pystray, session_bus_error
from scrollarea import MinimumSize, ScrollArea, Size, fitted_size
from settings import default_settings, setting_choices
from utils import resource_path, set_root_icon, start_task, task_wrapper, Game, _T
from constants import (
    MAX_INT,
    SELF_PATH,
    IS_PACKAGED,
    SCRIPTS_PATH,
    WINDOW_TITLE,
    LOGGING_LEVELS,
    OUTPUT_FORMATTER,
    State,
    PriorityMode,
)
from ui import (
    Notebook,
    LinkLabel,
    StatusBar,
    LoginForm,
    ChannelList,
    PaddedListbox,
    ConsoleOutput,
    MouseOverLabel,
    SelectCombobox,
    WebsocketStatus,
    CampaignProgress,
    PlaceholderEntry,
    _TKOutputHandler,
    PlaceholderCombobox,
)

if TYPE_CHECKING:
    from twitch import Twitch
    from settings import Settings
    from inventory import DropsCampaign, TimedDrop


logger = logging.getLogger("TwitchDrops")
pystray = import_pystray(load_pystray, os.environ, sys.platform, session_bus_error)


class TrayIcon:
    TITLE = "Twitch Drops Miner"

    def __init__(self, manager: GUIManager, master: ttk.Widget):
        self._manager = manager
        self.icon: pystray.Icon | None = None  # type: ignore[unused-ignore]
        self._icon_images: dict[str, Image_module.Image] = {
            "pickaxe": Image_module.open(resource_path("icons/pickaxe.ico")),
            "active": Image_module.open(resource_path("icons/active.ico")),
            "idle": Image_module.open(resource_path("icons/idle.ico")),
            "error": Image_module.open(resource_path("icons/error.ico")),
            "maint": Image_module.open(resource_path("icons/maint.ico")),
        }
        self._icon_state: str = "pickaxe"
        self._button = ttk.Button(master, command=self.minimize, text=_("gui", "tray", "minimize"))

        # Hides Tray button for macOS
        if sys.platform != "darwin":
            self._button.grid(column=0, row=0, sticky="ne")

    def __del__(self) -> None:
        self.stop()
        for icon_image in self._icon_images.values():
            icon_image.close()

    def _shorten(self, text: str, by_len: int, min_len: int) -> str:
        if (text_len := len(text)) <= min_len + 3 or by_len <= 0:
            # cannot shorten
            return text
        return text[:-min(by_len + 3, text_len - min_len)] + "..."

    def get_title(self, drop: TimedDrop | None) -> str:
        if drop is None:
            return self.TITLE
        campaign = drop.campaign
        title_parts: list[str] = [
            f"{self.TITLE}\n",
            campaign.game.name,
            "\n",
            drop.rewards_text(),
            f" {drop.progress:.1%} ({campaign.claimed_drops}/{campaign.total_drops})"
        ]
        min_len: int = 30
        max_len: int = 127
        missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            # try shortening the reward text
            title_parts[3] = self._shorten(title_parts[3], missing_len, min_len)
            missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            # try shortening the game name
            title_parts[1] = self._shorten(title_parts[1], missing_len, min_len)
            missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            raise MinerException(f"Title couldn't be shortened: {''.join(title_parts)}")
        return ''.join(title_parts)

    def _start(self):
        loop = asyncio.get_running_loop()
        drop = self._manager.progress._drop

        # we need this because tray icon lives in a separate thread
        def bridge(func):
            return lambda: loop.call_soon_threadsafe(func)

        menu = pystray.Menu(
            pystray.MenuItem(_("gui", "tray", "show"), bridge(self.restore), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("gui", "tray", "quit"), bridge(self.quit)),
        )
        self.icon = icon_class(pystray.Icon)(
            "twitch_miner", self._icon_images[self._icon_state], self.get_title(drop), menu
        )
        # self.icon.run_detached()
        loop.run_in_executor(None, self.icon.run)

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def quit(self):
        self._manager.close()

    def minimize(self):
        if sys.platform == "darwin":
            return
        if self.icon is None:
            self._start()
        else:
            self.icon.visible = True
        self._manager._root.withdraw()

    def restore(self):
        if self.icon is not None:
            if hides_by_stopping(self.icon):
                self.stop()
            else:
                self.icon.visible = False
        self._manager._root.deiconify()

    def notify(
        self, message: str, title: str | None = None, duration: float = 10
    ) -> asyncio.Task[None] | None:
        # do nothing if the user disabled notifications
        if not self._manager._twitch.settings.tray_notifications:
            return None
        if self.icon is not None:
            icon = self.icon  # nonlocal scope bind

            async def notifier():
                icon.notify(message, title)
                await asyncio.sleep(duration)
                icon.remove_notification()

            return asyncio.create_task(notifier())
        return None

    def update_title(self, drop: TimedDrop | None):
        if self.icon is not None:
            self.icon.title = self.get_title(drop)

    def change_icon(self, state: str):
        if state not in self._icon_images:
            raise ValueError("Invalid icon state")
        self._icon_state = state
        if self.icon is not None:
            self.icon.icon = self._icon_images[state]


class CampaignDisplay(TypedDict):
    frame: ttk.Frame
    status: ttk.Label


class InventoryOverview:
    def __init__(self, manager: GUIManager, master: ttk.Widget):
        self._manager = manager
        self._cache: ImageCache = manager._cache
        self._settings: Settings = manager._twitch.settings
        self._filters = {
            "not_linked": IntVar(
                master, self._settings.priority_mode is PriorityMode.PRIORITY_ONLY
            ),
            "upcoming": IntVar(master, 1),
            "expired": IntVar(master, 0),
            "excluded": IntVar(master, 0),
            "finished": IntVar(master, 0),
        }
        manager.tabs.add_view_event(self._on_tab_switched)
        # Filtering options
        filter_frame = ttk.LabelFrame(
            master, text=_("gui", "inventory", "filter", "name"), padding=(4, 0, 4, 4)
        )
        LABEL_SPACING = 20
        filter_frame.grid(column=0, row=0, columnspan=2, sticky="nsew")
        ttk.Label(
            filter_frame, text=_("gui", "inventory", "filter", "show"), padding=(0, 0, 10, 0)
        ).grid(column=0, row=0)
        icolumn = 0
        ttk.Checkbutton(
            filter_frame, variable=self._filters["not_linked"]
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Label(
            filter_frame,
            text=_("gui", "inventory", "filter", "not_linked"),
            padding=(0, 0, LABEL_SPACING, 0),
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Checkbutton(
            filter_frame, variable=self._filters["upcoming"]
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Label(
            filter_frame,
            text=_("gui", "inventory", "filter", "upcoming"),
            padding=(0, 0, LABEL_SPACING, 0),
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Checkbutton(
            filter_frame, variable=self._filters["expired"]
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Label(
            filter_frame,
            text=_("gui", "inventory", "filter", "expired"),
            padding=(0, 0, LABEL_SPACING, 0),
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Checkbutton(
            filter_frame, variable=self._filters["excluded"]
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Label(
            filter_frame,
            text=_("gui", "inventory", "filter", "excluded"),
            padding=(0, 0, LABEL_SPACING, 0),
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Checkbutton(
            filter_frame, variable=self._filters["finished"]
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Label(
            filter_frame,
            text=_("gui", "inventory", "filter", "finished"),
            padding=(0, 0, LABEL_SPACING, 0),
        ).grid(column=(icolumn := icolumn + 1), row=0)
        ttk.Button(
            filter_frame, text=_("gui", "inventory", "filter", "refresh"), command=self.refresh
        ).grid(column=(icolumn := icolumn + 1), row=0)
        # Inventory view
        self._area = ScrollArea(master, row=1)
        self._main_frame = self._area.inner
        self._campaigns: dict[DropsCampaign, CampaignDisplay] = {}
        self._drops: dict[str, ttk.Label] = {}

    def _update_visibility(self, campaign: DropsCampaign):
        # True if the campaign is supposed to show, False makes it hidden.
        frame = self._campaigns[campaign]["frame"]
        not_linked = bool(self._filters["not_linked"].get())
        expired = bool(self._filters["expired"].get())
        excluded = bool(self._filters["excluded"].get())
        upcoming = bool(self._filters["upcoming"].get())
        finished = bool(self._filters["finished"].get())
        priority_only = self._settings.priority_mode is PriorityMode.PRIORITY_ONLY
        # NOTE: list entries can be wildcards, so these need matching rather than a lookup
        game_name: str = campaign.game.name
        listed_excluded = any_match(compile_patterns(self._settings.exclude), game_name)
        listed_priority = any_match(compile_patterns(self._settings.priority), game_name)
        detected = game_name in self._settings.detected_games
        if (
            campaign.required_minutes > 0  # don't show sub-only campaigns
            and (not_linked or campaign.eligible)
            and (campaign.active or upcoming and campaign.upcoming or expired and campaign.expired)
            # the list rule of State.GAMES_UPDATE, so that the tab shows the games the app mines
            and (
                excluded or (
                    not listed_excluded
                    and (not priority_only or listed_priority or detected)
                )
            )
            and (finished or not campaign.finished)
        ):
            frame.grid()
        else:
            frame.grid_remove()

    def _on_tab_switched(self, event: tk.Event[ttk.Notebook]) -> None:
        if self._manager.tabs.current_tab() == 1:
            # refresh only if we're switching to the tab
            self.refresh()

    def get_status(self, campaign: DropsCampaign) -> tuple[str, str]:
        if campaign.active:
            status_text: str = _("gui", "inventory", "status", "active")
            status_color: str = "green"
        elif campaign.upcoming:
            status_text = _("gui", "inventory", "status", "upcoming")
            status_color = "goldenrod"
        else:
            status_text = _("gui", "inventory", "status", "expired")
            status_color = "red"
        return (status_text, status_color)

    def refresh(self):
        for campaign in self._campaigns:
            # status
            status_label = self._campaigns[campaign]["status"]
            status_text, status_color = self.get_status(campaign)
            status_label.config(text=status_text, foreground=status_color)
            # visibility
            self._update_visibility(campaign)
        self._area.update_region()

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        campaign_frame = ttk.Frame(self._main_frame, relief="ridge", borderwidth=1, padding=4)
        campaign_frame.grid(column=0, row=len(self._campaigns), sticky="nsew", pady=3)
        campaign_frame.rowconfigure(4, weight=1)
        campaign_frame.columnconfigure(1, weight=1)
        campaign_frame.columnconfigure(3, weight=10000)
        # Name
        ttk.Label(
            campaign_frame, text=campaign.name, takefocus=False, width=45
        ).grid(column=0, row=0, columnspan=2, sticky="w")
        # Status
        status_text, status_color = self.get_status(campaign)
        status_label = ttk.Label(
            campaign_frame, text=status_text, takefocus=False, foreground=status_color
        )
        status_label.grid(column=1, row=1, sticky="w", padx=4)
        # NOTE: We have to save the campaign's frame and status before any awaits happen,
        # otherwise the len(self._campaigns) call may overwrite an existing frame,
        # if the campaigns are added concurrently.
        self._campaigns[campaign] = {
            "frame": campaign_frame,
            "status": status_label,
        }
        # Starts / Ends
        MouseOverLabel(
            campaign_frame,
            text=_("gui", "inventory", "ends").format(
                time=campaign.ends_at.astimezone().replace(microsecond=0, tzinfo=None)
            ),
            alt_text=_("gui", "inventory", "starts").format(
                time=campaign.starts_at.astimezone().replace(microsecond=0, tzinfo=None)
            ),
            reverse=campaign.upcoming,
            takefocus=False,
        ).grid(column=1, row=2, sticky="w", padx=4)
        # Linking status
        if campaign.eligible:
            link_kwargs = {
                "style": '',
                "text": _("gui", "inventory", "status", "linked"),
                "foreground": "green",
            }
        else:
            link_kwargs = {
                "text": _("gui", "inventory", "status", "not_linked"),
                "foreground": "red",
            }
        LinkLabel(
            campaign_frame,
            link=campaign.link_url,
            takefocus=False,
            padding=0,
            **link_kwargs,
        ).grid(column=1, row=3, sticky="w", padx=4)
        # ACL channels
        acl = campaign.allowed_channels
        if acl:
            if len(acl) <= 5:
                allowed_text: str = '\n'.join(ch.name for ch in acl)
            else:
                allowed_text = '\n'.join(ch.name for ch in acl[:4])
                allowed_text += (
                    f"\n{_('gui', 'inventory', 'and_more').format(amount=len(acl) - 4)}"
                )
        else:
            allowed_text = _("gui", "inventory", "all_channels")
        ttk.Label(
            campaign_frame,
            text=f"{_('gui', 'inventory', 'allowed_channels')}\n{allowed_text}",
            takefocus=False,
        ).grid(column=1, row=4, sticky="nw", padx=4)
        # Image
        campaign_image = await self._cache.get(campaign.image_url, size=(108, 144))
        ttk.Label(campaign_frame, image=campaign_image).grid(column=0, row=1, rowspan=4)
        # Drops separator
        ttk.Separator(
            campaign_frame, orient="vertical", takefocus=False
        ).grid(column=2, row=0, rowspan=5, sticky="ns")
        # Drops display
        drops_row = ttk.Frame(campaign_frame)
        drops_row.grid(column=3, row=0, rowspan=5, sticky="nsew", padx=4)
        drops_row.rowconfigure(0, weight=1)
        for i, drop in enumerate(campaign.drops):
            drop_frame = ttk.Frame(drops_row, relief="ridge", borderwidth=1, padding=5)
            drop_frame.grid(column=i, row=0, padx=4)
            benefits_frame = ttk.Frame(drop_frame)
            benefits_frame.grid(column=0, row=0)
            benefit_images: list[PhotoImage] = await asyncio.gather(
                *(self._cache.get(benefit.image_url, (80, 80)) for benefit in drop.benefits)
            )
            for i, benefit, image in zip(range(len(drop.benefits)), drop.benefits, benefit_images):
                ttk.Label(
                    benefits_frame,
                    text=benefit.name,
                    image=image,
                    compound="bottom",
                ).grid(column=i, row=0, padx=5)
            self._drops[drop.id] = label = ttk.Label(drop_frame, justify=tk.CENTER)
            self.update_progress(drop, label)
            label.grid(column=0, row=1)
        if self._manager.tabs.current_tab() == 1:
            self._update_visibility(campaign)
            self._area.update_region()

    def clear(self) -> None:
        for child in self._main_frame.winfo_children():
            child.destroy()
        self._drops.clear()
        self._campaigns.clear()
        # fetch_inventory calls this once per reload, so each failed image download is tried once per reload
        self._cache.retry_failed()

    def update_progress(self, drop: TimedDrop, label: ttk.Label) -> None:
        progress_text: str
        progress_color: str = ''
        if drop.is_claimed:
            progress_color = "green"
            progress_text = _("gui", "inventory", "status", "claimed")
        elif drop.can_claim:
            progress_color = "goldenrod"
            progress_text = _("gui", "inventory", "status", "ready_to_claim")
        elif drop.current_minutes or drop.can_earn():
            progress_text = _("gui", "inventory", "percent_progress").format(
                percent=f"{drop.progress:3.1%}",
                minutes=drop.required_minutes,
            )
            if drop.ends_at < drop.campaign.ends_at:
                # this drop becomes unavailable earlier than the campaign ends
                progress_text += '\n' + _("gui", "inventory", "ends").format(
                    time=drop.ends_at.astimezone().replace(microsecond=0, tzinfo=None)
                )
        else:
            if drop.required_minutes > 0:
                progress_text = _("gui", "inventory", "minutes_progress").format(
                    minutes=drop.required_minutes
                )
            else:
                # required_minutes is zero for subscription-based drops
                progress_text = ''
            if datetime.now(timezone.utc) < drop.starts_at > drop.campaign.starts_at:
                # this drop starts later than its campaign
                progress_text += '\n' + _("gui", "inventory", "starts").format(
                    time=drop.starts_at.astimezone().replace(microsecond=0, tzinfo=None)
                )
            elif drop.ends_at < drop.campaign.ends_at:
                # this drop becomes unavailable earlier than the campaign ends
                progress_text += '\n' + _("gui", "inventory", "ends").format(
                    time=drop.ends_at.astimezone().replace(microsecond=0, tzinfo=None)
                )
        label.config(text=progress_text, foreground=progress_color)

    def update_drop(self, drop: TimedDrop) -> None:
        label = self._drops.get(drop.id)
        if label is None:
            return
        self.update_progress(drop, label)


def proxy_validate(entry: PlaceholderEntry, settings: Settings) -> bool:
    raw_url = entry.get().strip()
    entry.replace(raw_url)
    url = URL(raw_url)
    valid = url.host is not None and url.port is not None
    if not valid:
        entry.clear()
        url = URL()
    settings.proxy = url
    return valid


class _SettingsVars(TypedDict):
    tray: IntVar
    proxy: StringVar
    autostart: IntVar
    dark_mode: IntVar
    language: StringVar
    priority_mode: StringVar
    refresh_interval: StringVar
    restart_delay: StringVar
    tray_notifications: IntVar
    enable_badges_emotes: IntVar
    available_drops_check: IntVar


class SettingsPanel:
    @cached_property
    def PRIORITY_MODES(self) -> dict[PriorityMode, str]:
        # NOTE: Translation calls have to be deferred here,
        # to allow changing the language before the settings panel is initialized.
        names: dict[PriorityMode, str] = {
            PriorityMode.PRIORITY_ONLY: _("gui", "settings", "priority_modes", "priority_only"),
            PriorityMode.ENDING_SOONEST: _("gui", "settings", "priority_modes", "ending_soonest"),
            PriorityMode.LOW_AVBL_FIRST: _(
                "gui", "settings", "priority_modes", "low_availability"
            ),
        }
        return {mode: names[mode] for mode in setting_choices["priority_mode"]}

    @cached_property
    def REFRESH_INTERVALS(self) -> dict[int, str]:
        # NOTE: Translation calls have to be deferred here,
        # to allow changing the language before the settings panel is initialized.
        return {
            minutes: (
                _("gui", "settings", "refresh_intervals", "minutes").format(minutes=minutes)
                if minutes
                else _("gui", "settings", "refresh_intervals", "disabled")
            )
            for minutes in setting_choices["refresh_interval"]
        }

    @cached_property
    def RESTART_DELAYS(self) -> dict[int, str]:
        # NOTE: Translation calls have to be deferred here,
        # to allow changing the language before the settings panel is initialized.
        return {
            minutes: (
                _("gui", "settings", "restart_delays", "minutes").format(minutes=minutes)
                if minutes
                else _("gui", "settings", "restart_delays", "disabled")
            )
            for minutes in setting_choices["restart_delay"]
        }

    def __init__(self, manager: GUIManager, master: ttk.Widget):
        self._manager = manager
        self._settings: Settings = manager._twitch.settings
        self._folder_picker = FolderPicker()
        self._autostart: AutostartEntry = autostart_entry(sys.platform, os.environ, Path.home())
        priority_mode = self._settings.priority_mode
        if priority_mode not in self.PRIORITY_MODES:
            priority_mode = default_settings["priority_mode"]
            self._settings.priority_mode = priority_mode
        refresh_interval = self._settings.refresh_interval
        if refresh_interval not in self.REFRESH_INTERVALS:
            refresh_interval = default_settings["refresh_interval"]
            self._settings.refresh_interval = refresh_interval
        restart_delay = self._settings.restart_delay
        if restart_delay not in self.RESTART_DELAYS:
            restart_delay = default_settings["restart_delay"]
            self._settings.restart_delay = restart_delay
        self._vars: _SettingsVars = {
            "autostart": IntVar(master, 0),
            "language": StringVar(master, _.current),
            "proxy": StringVar(master, str(self._settings.proxy)),
            "tray": IntVar(master, self._settings.autostart_tray),
            "dark_mode": IntVar(master, int(self._settings.dark_mode)),
            "priority_mode": StringVar(master, self.PRIORITY_MODES[priority_mode]),
            "refresh_interval": StringVar(master, self.REFRESH_INTERVALS[refresh_interval]),
            "restart_delay": StringVar(master, self.RESTART_DELAYS[restart_delay]),
            "tray_notifications": IntVar(master, self._settings.tray_notifications),
            "enable_badges_emotes": IntVar(
                master, int(self._settings.enable_badges_emotes)
            ),
            "available_drops_check": IntVar(
                master, int(self._settings.available_drops_check)
            ),
        }
        self._game_names: set[str] = set()
        # the content scrolls in a window smaller than it, so it does not set the minimum window size
        self._area = ScrollArea(master, row=0, fit=True)
        center_frame = self._area.inner

        # Mining summary section
        # NOTE: spans the full width above the other sections, filling what would
        # otherwise be dead space, and answers "so what is it actually mining?"
        wanted_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "wanted", "name")
        )
        wanted_frame.grid(column=0, row=0, columnspan=4, sticky="nsew", pady=(0, 4))
        wanted_frame.columnconfigure(0, weight=1)
        wanted_frame.rowconfigure(0, weight=1)
        wanted_scroll = ttk.Scrollbar(wanted_frame, orient="vertical")
        self._wanted_table = ttk.Treeview(
            wanted_frame,
            height=6,
            show="headings",
            selectmode="none",
            columns=("order", "game", "source"),
            yscrollcommand=wanted_scroll.set,
        )
        wanted_scroll.config(command=self._wanted_table.yview)
        self._wanted_table.grid(column=0, row=0, sticky="nsew")
        wanted_scroll.grid(column=1, row=0, sticky="ns")
        self._wanted_table.heading("order", text="#")
        self._wanted_table.heading("game", text=_("gui", "settings", "wanted", "game"))
        self._wanted_table.heading("source", text=_("gui", "settings", "wanted", "source"))
        self._wanted_table.column("order", width=40, stretch=False, anchor="center")
        self._wanted_table.column("game", width=460, anchor='w')
        self._wanted_table.column("source", width=300, anchor='w')
        self._wanted_label = ttk.Label(
            wanted_frame, text=_("gui", "settings", "wanted", "empty")
        )
        self._wanted_label.grid(column=0, row=1, columnspan=2, sticky="w", pady=(2, 0))

        # General section
        general_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "general", "name")
        )
        general_frame.grid(column=0, row=1, sticky="nsew")
        # use another frame to center the options within the section
        # NOTE: this can be adjusted or removed later on if more options were to be added
        general_frame.rowconfigure(0, weight=1)
        general_frame.columnconfigure(0, weight=1)
        general_center = ttk.Frame(general_frame)
        general_center.grid(column=0, row=0)

        # language frame
        language_frame = ttk.Frame(general_center)
        language_frame.grid(column=0, row=0)
        language_text: str = _("gui", "settings", "general", "language")
        if language_text != default_translation["gui"]["settings"]["general"]["language"]:
            # a user who picked a language they cannot read still finds the setting by its English name
            language_text = f"Language / {language_text}"
        ttk.Label(language_frame, text=language_text).grid(column=0, row=0)
        SelectCombobox(
            language_frame,
            values=list(_.languages),
            textvariable=self._vars["language"],
            command=lambda e: setattr(self._settings, "language", self._vars["language"].get()),
        ).grid(column=1, row=0)

        # checkboxes frame
        checkboxes_frame = ttk.Frame(general_center)
        checkboxes_frame.grid(column=0, row=1)
        ttk.Label(
            checkboxes_frame, text=_("gui", "settings", "general", "autostart")
        ).grid(column=0, row=(irow := 0), sticky="e")
        ttk.Checkbutton(
            checkboxes_frame, variable=self._vars["autostart"], command=self.update_autostart
        ).grid(column=1, row=irow, sticky="w")
        self._vars["autostart"].set(self._query_autostart())
        if sys.platform != "darwin":
            ttk.Label(
                checkboxes_frame, text=_("gui", "settings", "general", "tray")
            ).grid(column=0, row=(irow := irow + 1), sticky="e")
            ttk.Checkbutton(
                checkboxes_frame, variable=self._vars["tray"], command=self.update_autostart
            ).grid(column=1, row=irow, sticky="w")
            ttk.Label(
                checkboxes_frame, text=_("gui", "settings", "general", "tray_notifications")
            ).grid(column=0, row=(irow := irow + 1), sticky="e")
            ttk.Checkbutton(
                checkboxes_frame,
                variable=self._vars["tray_notifications"],
                command=lambda: setattr(
                    self._settings,
                    "tray_notifications",
                    bool(self._vars["tray_notifications"].get()),
                ),
            ).grid(column=1, row=irow, sticky="w")
        ttk.Label(
            checkboxes_frame, text=_("gui", "settings", "general", "dark_mode")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        ttk.Checkbutton(
            checkboxes_frame,
            variable=self._vars["dark_mode"],
            command=self.update_dark_mode,
        ).grid(column=1, row=irow, sticky="w")
        ttk.Label(
            checkboxes_frame, text=_("gui", "settings", "general", "priority_mode")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        SelectCombobox(
            checkboxes_frame,
            command=self.priority_mode,
            textvariable=self._vars["priority_mode"],
            values=list(self.PRIORITY_MODES.values()),
        ).grid(column=1, row=irow, sticky="w")
        ttk.Label(
            checkboxes_frame, text=_("gui", "settings", "general", "refresh_interval")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        SelectCombobox(
            checkboxes_frame,
            command=self.refresh_interval,
            textvariable=self._vars["refresh_interval"],
            values=list(self.REFRESH_INTERVALS.values()),
        ).grid(column=1, row=irow, sticky="w")
        ttk.Label(
            checkboxes_frame, text=_("gui", "settings", "general", "restart_delay")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        SelectCombobox(
            checkboxes_frame,
            command=self.restart_delay,
            textvariable=self._vars["restart_delay"],
            values=list(self.RESTART_DELAYS.values()),
        ).grid(column=1, row=irow, sticky="w")

        # proxy frame
        proxy_frame = ttk.Frame(general_center)
        proxy_frame.grid(column=0, row=2)
        ttk.Label(proxy_frame, text=_("gui", "settings", "general", "proxy")).grid(column=0, row=0)
        self._proxy = PlaceholderEntry(
            proxy_frame,
            width=37,
            validate="focusout",
            prefill="http://",
            textvariable=self._vars["proxy"],
            placeholder="http://username:password@address:port",
        )
        self._proxy.config(validatecommand=partial(proxy_validate, self._proxy, self._settings))
        self._proxy.grid(column=0, row=1)

        # Advanced section
        advanced_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "advanced", "name")
        )
        advanced_frame.grid(column=0, row=2, sticky="nsew")
        advanced_frame.columnconfigure(0, weight=1)
        advanced_frame.rowconfigure(0, weight=1)
        advanced_center = ttk.Frame(advanced_frame)
        advanced_center.grid(column=0, row=0)

        # Warning message
        ttk.Label(
            advanced_center, text=_("gui", "settings", "advanced", "warning"), foreground="red"
        ).grid(column=0, row=(irow := 0), columnspan=2)
        ttk.Label(
            advanced_center,
            text=_("gui", "settings", "advanced", "warning_text"),
            foreground="goldenrod",
        ).grid(column=0, row=(irow := irow + 1), columnspan=2)
        # Toggles for badges and emotes, and available drops check
        ttk.Label(
            advanced_center, text=_("gui", "settings", "advanced", "enable_badges_emotes")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        ttk.Checkbutton(
            advanced_center,
            variable=self._vars["enable_badges_emotes"],
            command=lambda: setattr(
                self._settings,
                "enable_badges_emotes",
                bool(self._vars["enable_badges_emotes"].get()),
            ),
        ).grid(column=1, row=irow, sticky="w")
        ttk.Label(
            advanced_center, text=_("gui", "settings", "advanced", "available_drops_check")
        ).grid(column=0, row=(irow := irow + 1), sticky="e")
        ttk.Checkbutton(
            advanced_center,
            variable=self._vars["available_drops_check"],
            command=lambda: setattr(
                self._settings,
                "available_drops_check",
                bool(self._vars["available_drops_check"].get()),
            ),
        ).grid(column=1, row=irow, sticky="w")

        # Priority section
        priority_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "priority")
        )
        priority_frame.grid(column=1, row=1, rowspan=2, sticky="nsew")
        self._priority_entry = PlaceholderCombobox(
            priority_frame, placeholder=_("gui", "settings", "game_name"), width=30
        )
        self._priority_entry.grid(column=0, row=0, sticky="ew")
        priority_frame.columnconfigure(0, weight=1)
        ttk.Button(
            priority_frame, text="➕", command=self.priority_add, width=3, style="Large.TButton"
        ).grid(column=1, row=0, sticky="nsew")
        self._priority_list = PaddedListbox(
            priority_frame,
            height=12,
            padding=(1, 0),
            activestyle="none",
            selectmode="single",
            highlightthickness=0,
            exportselection=False,
        )
        self._priority_list.grid(column=0, row=1, rowspan=5, sticky="nsew")
        self._priority_list.insert("end", *self._settings.priority)
        weight_scale: int = 5
        ttk.Button(  # Move to top
            priority_frame,
            width=2,
            text="⇈",
            style="Arrow.TButton",
            command=partial(self.priority_move, MAX_INT),
        ).grid(column=1, row=1, sticky="nsew")
        priority_frame.rowconfigure(1, weight=1)
        ttk.Button(  # Move up
            priority_frame,
            width=2,
            text="↑",
            style="Arrow.TButton",
            command=partial(self.priority_move, 1),
        ).grid(column=1, row=2, sticky="nsew")
        priority_frame.rowconfigure(2, weight=weight_scale)
        ttk.Button(  # Move down
            priority_frame,
            width=2,
            text="↓",
            style="Arrow.TButton",
            command=partial(self.priority_move, -1),
        ).grid(column=1, row=3, sticky="nsew")
        priority_frame.rowconfigure(3, weight=weight_scale)
        ttk.Button(  # Move to bottom
            priority_frame,
            width=2,
            text="⇊",
            style="Arrow.TButton",
            command=partial(self.priority_move, -MAX_INT),
        ).grid(column=1, row=4, sticky="nsew")
        priority_frame.rowconfigure(4, weight=1)
        ttk.Button(
            priority_frame, text="❌", command=self.priority_delete, width=3, style="Large.TButton"
        ).grid(column=1, row=5, sticky="nsew")
        priority_frame.rowconfigure(5, weight=1)

        # Exclude section
        exclude_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "exclude")
        )
        exclude_frame.grid(column=2, row=1, rowspan=2, sticky="nsew")
        self._exclude_entry = PlaceholderCombobox(
            exclude_frame, placeholder=_("gui", "settings", "game_name"), width=26
        )
        self._exclude_entry.grid(column=0, row=0, sticky="ew")
        ttk.Button(
            exclude_frame, text="➕", command=self.exclude_add, width=3, style="Large.TButton"
        ).grid(column=1, row=0)
        self._exclude_list = PaddedListbox(
            exclude_frame,
            height=12,
            padding=(1, 0),
            activestyle="none",
            selectmode="single",
            highlightthickness=0,
            exportselection=False,
        )
        self._exclude_list.grid(column=0, row=1, columnspan=2, sticky="nsew")
        exclude_frame.rowconfigure(1, weight=1)
        # insert them alphabetically
        self._exclude_list.insert("end", *sorted(self._settings.exclude))
        ttk.Button(
            exclude_frame, text="❌", command=self.exclude_delete, width=3, style="Large.TButton"
        ).grid(column=0, row=2, columnspan=2, sticky="nsew")

        # Detected games section
        detect_frame = ttk.LabelFrame(
            center_frame, padding=(4, 0, 4, 4), text=_("gui", "settings", "detect", "name")
        )
        detect_frame.grid(column=3, row=1, rowspan=2, sticky="nsew")
        detect_frame.columnconfigure(0, weight=1)
        # NOTE: this list is filled in automatically and has no add/remove buttons on purpose.
        # To override a bad match, put the game on the Exclude list - that's checked separately
        # and wins over everything else.
        self._detected_list = PaddedListbox(
            detect_frame,
            width=28,
            height=8,
            padding=(1, 0),
            activestyle="none",
            selectmode="single",
            highlightthickness=0,
            exportselection=False,
        )
        self._detected_list.grid(column=0, row=0, columnspan=2, sticky="nsew")
        detect_frame.rowconfigure(0, weight=3)
        self._detected_label = ttk.Label(
            detect_frame, text=_("gui", "settings", "detect", "empty"), wraplength=210
        )
        self._detected_label.grid(column=0, row=1, columnspan=2, sticky="ew", pady=(2, 4))
        ttk.Label(
            detect_frame, text=_("gui", "settings", "detect", "dirs")
        ).grid(column=0, row=2, columnspan=2, sticky="w")
        self._game_dirs_list = PaddedListbox(
            detect_frame,
            width=28,
            height=4,
            padding=(1, 0),
            activestyle="none",
            selectmode="single",
            highlightthickness=0,
            exportselection=False,
        )
        self._game_dirs_list.grid(column=0, row=3, rowspan=2, sticky="nsew")
        detect_frame.rowconfigure(3, weight=1)
        self._game_dir_add_button = ttk.Button(
            detect_frame, text="➕", command=self.game_dir_add, width=3, style="Large.TButton"
        )
        self._game_dir_add_button.grid(column=1, row=3, sticky="nsew")
        ttk.Button(
            detect_frame,
            text="❌",
            width=3,
            style="Large.TButton",
            command=self.game_dir_delete,
        ).grid(column=1, row=4, sticky="nsew")
        ttk.Button(
            detect_frame,
            text=_("gui", "settings", "detect", "rescan"),
            command=self.rescan_games,
        ).grid(column=0, row=5, columnspan=2, sticky="ew", pady=(4, 0))
        # restore what the last scan found, so the list isn't empty before the first reload
        self._game_dirs_list.insert("end", *self._settings.game_dirs)
        self._restore_detected()

        # Reload button
        reload_frame = ttk.Frame(center_frame)
        reload_frame.grid(column=0, row=3, columnspan=4, pady=4)
        ttk.Label(reload_frame, text=_("gui", "settings", "reload_text")).grid(column=0, row=0)
        ttk.Button(
            reload_frame,
            text=_("gui", "settings", "reload"),
            command=self._manager._twitch.state_change(State.INVENTORY_FETCH),
        ).grid(column=1, row=0)

    def clear_selection(self) -> None:
        self._priority_list.selection_clear(0, "end")
        self._exclude_list.selection_clear(0, "end")
        self._detected_list.selection_clear(0, "end")
        self._game_dirs_list.selection_clear(0, "end")

    def update_dark_mode(self) -> None:
        self._settings.dark_mode = bool(self._vars["dark_mode"].get())
        self._manager.apply_theme(self._settings.dark_mode)

    def _get_autostart_path(self) -> str:
        python = None if IS_PACKAGED else source_python(SCRIPTS_PATH, sys.platform)
        return autostart_command(
            SELF_PATH.resolve(), self._settings.logging_level, bool(self._vars["tray"].get()), python
        )

    def _query_autostart(self) -> bool:
        return self._autostart.contains(SELF_PATH.resolve())

    def update_autostart(self) -> None:
        enabled = bool(self._vars["autostart"].get())
        self._settings.autostart_tray = bool(self._vars["tray"].get())
        try:
            if enabled:
                self._autostart.write(self._get_autostart_path())
            else:
                self._autostart.remove()
        except OSError as exc:
            logger.error(_("error", "autostart_not_changed").format(error=exc))
            self._vars["autostart"].set(self._query_autostart())

    def update_excluded_choices(self) -> None:
        self._exclude_entry.config(
            values=sorted(self._game_names.difference(self._settings.exclude))
        )

    def update_priority_choices(self) -> None:
        self._priority_entry.config(
            values=sorted(self._game_names.difference(self._settings.priority))
        )

    def set_games(self, games: set[Game]) -> None:
        self._game_names.update(game.name for game in games)
        self.update_excluded_choices()
        self.update_priority_choices()

    def set_wanted_games(self, games: abc.Sequence[Game]) -> None:
        """
        Show what the miner settled on mining, and what each game got there by.
        """
        table = self._wanted_table
        table.delete(*table.get_children())
        priority: list[str] = self._settings.priority
        patterns = compile_patterns(priority)
        detected: list[str] = self._settings.detected_games
        for index, game in enumerate(games, start=1):
            rank: int | None = match_rank(patterns, game.name)
            if rank is not None:
                # name the entry responsible, so a wildcard's reach is visible
                source: str = priority[rank]
            elif game.name in detected:
                source = _("gui", "settings", "wanted", "installed")
            else:
                # only reachable when the priority mode allows mining anything
                source = _("gui", "settings", "wanted", "unlisted")
            table.insert('', "end", values=(index, game.name, source))
        self._wanted_label.config(
            text=(
                _("gui", "settings", "wanted", "count").format(count=len(games))
                if games
                else _("gui", "settings", "wanted", "empty")
            )
        )

    def _fill_detected(self, entries: abc.Iterable[tuple[str, bool]]) -> None:
        self._detected_list.delete(0, "end")
        for game_name, exact in entries:
            # mark the names we had to guess at, so a wrong one is easy to spot
            self._detected_list.insert("end", game_name if exact else f"≈ {game_name}")

    def _restore_detected(self) -> None:
        """
        Show the previous scan's result, before a new scan has had a chance to run.
        """
        detected: list[str] = self._settings.detected_games
        # NOTE: only the names are persisted, so we can't tell exact matches apart here
        self._fill_detected((game_name, True) for game_name in detected)
        self._detected_label.config(
            text=(
                _("gui", "settings", "detect", "restored").format(count=len(detected))
                if detected
                else _("gui", "settings", "detect", "empty")
            )
        )

    def set_scanning(self, scanning: bool) -> None:
        if scanning:
            self._detected_label.config(text=_("gui", "settings", "detect", "scanning"))
        else:
            # scan didn't complete - put the previous result back rather than
            # leaving the label stuck on "scanning..."
            self._restore_detected()

    def set_detected(self, matches: abc.Sequence[GameMatch], installed: int = 0) -> None:
        self._fill_detected((m.game_name, m.kind is MatchKind.EXACT) for m in matches)
        if not self._settings.game_dirs:
            self._detected_label.config(text=_("gui", "settings", "detect", "no_dirs"))
            return
        self._detected_label.config(
            text=_("gui", "settings", "detect", "detected").format(
                count=sum(match.local_count for match in matches), total=installed
            )
        )

    def rescan_games(self) -> None:
        start_task(task_wrapper(self._manager._twitch.detect_games)())

    def game_dir_add(self) -> None:
        # the button stays disabled while the dialog is open, so only one dialog opens
        self._game_dir_add_button.state(["disabled"])
        start_task(task_wrapper(self._add_chosen_dir)())

    async def _add_chosen_dir(self) -> None:
        try:
            directory: str = await self._manager.coro_unless_closed(
                self._folder_picker.choose(_("gui", "settings", "detect", "add_dir"))
            )
        finally:
            self._game_dir_add_button.state(["!disabled"])
        if not directory:
            # dialog cancelled
            return
        # normalize the separators, so the same folder can't be added twice
        directory = str(Path(directory))
        if directory in self._settings.game_dirs:
            return
        self._settings.game_dirs.append(directory)
        self._settings.alter()
        self._game_dirs_list.insert("end", directory)
        self._game_dirs_list.see("end")
        self.rescan_games()

    def game_dir_delete(self) -> None:
        selection: tuple[int, ...] = self._game_dirs_list.curselection()
        if not selection:
            return
        idx: int = selection[0]
        self._game_dirs_list.delete(idx)
        del self._settings.game_dirs[idx]
        self._settings.alter()
        self.rescan_games()

    def _report_pattern(self, entry: str) -> None:
        """
        Say what a wildcard entry caught, so it isn't a shot in the dark.

        Plain entries are left alone - what they match is already obvious.
        """
        if not has_wildcard(entry):
            return
        matched: list[str] = matching_names(compile_pattern(entry), self._game_names)
        if matched:
            self._manager.print(
                _("gui", "settings", "pattern_matches").format(
                    pattern=entry, count=len(matched), games=", ".join(matched)
                )
            )
        else:
            self._manager.print(
                _("gui", "settings", "pattern_empty").format(pattern=entry)
            )

    def priority_add(self) -> None:
        game_name: str = self._priority_entry.get()
        if not game_name:
            # prevent adding empty strings
            return
        self._priority_entry.clear()
        # add it preventing duplicates
        try:
            existing_idx: int = self._settings.priority.index(game_name)
        except ValueError:
            # not there, add it
            self._priority_list.insert("end", game_name)
            self._priority_list.see("end")
            self._settings.priority.append(game_name)
            self._settings.alter()
            self.update_priority_choices()
            self._report_pattern(game_name)
        else:
            # already there, set the selection on it
            self._priority_list.selection_set(existing_idx)
            self._priority_list.see(existing_idx)

    def _priority_idx(self) -> int | None:
        selection: tuple[int, ...] = self._priority_list.curselection()
        if not selection:
            return None
        return selection[0]

    def priority_move(self, amount: int) -> None:
        # amount > 0 = up, amount < 0 = down
        idx: int | None = self._priority_idx()
        max_idx: int = self._priority_list.size() - 1
        if (
            idx is None
            or amount == 0
            or amount > 0 and idx == 0
            or amount < 0 and idx == max_idx
        ):
            return
        insert_idx: int = idx - amount
        if insert_idx <= 0:
            insert_idx = 0
        elif insert_idx >= max_idx:
            insert_idx = max_idx

        item: str = self._priority_list.get(idx)
        self._priority_list.delete(idx)
        self._priority_list.insert(insert_idx, item)
        # reselect the item and scroll the list if needed
        self._priority_list.selection_set(insert_idx)
        self._priority_list.see(insert_idx)
        # update the underlying settings list too
        self._settings.priority.pop(idx)
        self._settings.priority.insert(insert_idx, item)
        self._settings.alter()

    def priority_delete(self) -> None:
        idx: int | None = self._priority_idx()
        if idx is None:
            return
        self._priority_list.delete(idx)
        del self._settings.priority[idx]
        self._settings.alter()
        self.update_priority_choices()

    def priority_mode(self, event: tk.Event[ttk.Combobox]) -> None:
        mode_name: str = self._vars["priority_mode"].get()
        for value, name in self.PRIORITY_MODES.items():
            if mode_name == name:
                self._settings.priority_mode = value
                break

    def refresh_interval(self, event: tk.Event[ttk.Combobox]) -> None:
        interval_name: str = self._vars["refresh_interval"].get()
        for value, name in self.REFRESH_INTERVALS.items():
            if interval_name == name:
                self._settings.refresh_interval = value
                break

    def restart_delay(self, event: tk.Event[ttk.Combobox]) -> None:
        delay_name: str = self._vars["restart_delay"].get()
        for value, name in self.RESTART_DELAYS.items():
            if delay_name == name:
                self._settings.restart_delay = value
                break

    def exclude_add(self) -> None:
        game_name: str = self._exclude_entry.get()
        if not game_name:
            # prevent adding empty strings
            return
        self._exclude_entry.clear()
        if game_name not in self._settings.exclude:
            self._settings.exclude.add(game_name)
            self._settings.alter()
            self.update_excluded_choices()
            self._report_pattern(game_name)
            # insert it alphabetically
            for i, item in enumerate(self._exclude_list.get(0, "end")):
                if game_name < item:
                    self._exclude_list.insert(i, game_name)
                    self._exclude_list.see(i)
                    break
            else:
                self._exclude_list.insert("end", game_name)
                self._exclude_list.see("end")
        else:
            # it was already there, select it
            for i, item in enumerate(self._exclude_list.get(0, "end")):
                if item == game_name:
                    existing_idx = i
                    break
            else:
                # something went horribly wrong and it's not there after all - just return
                return
            self._exclude_list.selection_set(existing_idx)
            self._exclude_list.see(existing_idx)

    def exclude_delete(self) -> None:
        selection: tuple[int, ...] = self._exclude_list.curselection()
        if not selection:
            return None
        idx: int = selection[0]
        item: str = self._exclude_list.get(idx)
        if item in self._settings.exclude:
            self._exclude_list.delete(idx)
            self._settings.exclude.discard(item)
            self._settings.alter()
            self.update_excluded_choices()


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


##########################################
# GUI DEFINITION END / GUI MANAGER START #
##########################################


class GUIManager:
    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._poll_task: asyncio.Task[NoReturn] | None = None
        self._close_requested = asyncio.Event()
        skip_color_fonts(LoadedFontLibraries())
        self._root = root = Tk(className=WINDOW_TITLE)
        # withdraw immediately to prevent the window from flashing
        self._root.withdraw()
        # root.resizable(False, True)
        set_root_icon(root, resource_path("icons/pickaxe.ico"))
        root.title(WINDOW_TITLE)  # window title
        root.bind_all("<KeyPress-Escape>", self.unfocus)  # pressing ESC unfocuses selection
        # Image cache for displaying images
        self._cache = ImageCache(self)

        # style adjustements
        self._style = style = ttk.Style(root)
        # theme
        theme = ''
        # theme = style.theme_names()[6]
        # style.theme_use(theme)
        # fix treeview's background color from tags not working (also see '_fixed_map')
        style.map(
            "Treeview",
            foreground=self._fixed_map("foreground"),
            background=self._fixed_map("background"),
        )
        # add padding to the tab names
        style.configure("TNotebook.Tab", padding=[8, 4])
        # Skip these for classic theme or macOS
        if theme != "classic" and sys.platform != "darwin":
            # remove Notebook.focus from the Notebook.Tab layout tree to avoid an ugly dotted line
            # on tab selection. We fold the Notebook.focus children into Notebook.padding children.
            original = style.layout("TNotebook.Tab")
            sublayout = original[0][1]["children"][0][1]
            sublayout["children"] = sublayout["children"][0][1]["children"]
            style.layout("TNotebook.Tab", original)
            # remove Checkbutton.focus dotted line from checkbuttons
            style.configure("TCheckbutton", padding=0)
            original = style.layout("TCheckbutton")
            sublayout = original[0][1]["children"]
            sublayout[1] = sublayout[1][1]["children"][0]
            del original[0][1]["children"][1]
            style.layout("TCheckbutton", original)
        # label style - green, yellow and red text
        style.configure("green.TLabel", foreground="green")
        style.configure("yellow.TLabel", foreground="goldenrod")
        style.configure("red.TLabel", foreground="red")
        # fonts storage
        self._fonts: dict[str, Font] = {}
        # end of style changes

        root_frame = ttk.Frame(root, padding=8)
        root_frame.grid(column=0, row=0, sticky="nsew")
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        # Notebook
        self.tabs = Notebook(self, root_frame)
        # Tray icon - place after notebook so it draws on top of the tabs space
        self.tray = TrayIcon(self, root_frame)
        # Main tab
        main_frame = ttk.Frame(root_frame, padding=8)
        self.tabs.add_tab(main_frame, name=_("gui", "tabs", "main"))
        self.status = StatusBar(self, main_frame)
        self.websockets = WebsocketStatus(self, main_frame)
        self.login = LoginForm(self, main_frame)
        self.progress = CampaignProgress(self, main_frame)
        self.output = ConsoleOutput(self, main_frame)
        self.channels = ChannelList(self, main_frame)
        # Inventory tab
        inv_frame = ttk.Frame(root_frame, padding=8)
        self.inv = InventoryOverview(self, inv_frame)
        self.tabs.add_tab(inv_frame, name=_("gui", "tabs", "inventory"))
        # Settings tab
        settings_frame = ttk.Frame(root_frame, padding=8)
        self.settings = SettingsPanel(self, settings_frame)
        self.tabs.add_tab(settings_frame, name=_("gui", "tabs", "settings"))
        # Help tab
        help_frame = ttk.Frame(root_frame, padding=8)
        self.help = HelpTab(self, help_frame)
        self.tabs.add_tab(help_frame, name=_("gui", "tabs", "help"))
        # the Settings tab scrolls and the Output box can show fewer lines, so the minimum window size leaves them out
        self._minimum = MinimumSize(
            root,
            root_frame,
            (main_frame, inv_frame, help_frame),
            (self.settings._area.collapsed, self.output.shortened),
        )
        # register logging handler
        self._handler = _TKOutputHandler(self)
        self._handler.setFormatter(OUTPUT_FORMATTER)
        logger = logging.getLogger("TwitchDrops")
        logger.addHandler(self._handler)
        if (logging_level := logger.getEffectiveLevel()) < logging.ERROR:
            self.print(_("status", "logging_level").format(level=logging.getLevelName(logging_level)))
        # gracefully handle Windows shutdown closing the application
        if sys.platform == "win32":
            # NOTE: this root.update() is required for the below to work - don't remove
            root.update()
            self._message_map = {
                # window close request
                win32con.WM_CLOSE: self.close,
                # shutdown request
                win32con.WM_QUERYENDSESSION: self.close,
            }
            # This hooks up the wnd_proc function as the message processor for the root window.
            self.old_wnd_proc = win32gui.SetWindowLong(
                self._handle, win32con.GWL_WNDPROC, self.wnd_proc
            )
            # This ensures all of this works when the application is withdrawn or iconified
            ctypes.windll.user32.ShutdownBlockReasonCreate(
                self._handle, ctypes.c_wchar_p(_("gui", "status", "exiting"))
            )
            # DEV NOTE: use this to remove the reason in the future
            # ctypes.windll.user32.ShutdownBlockReasonDestroy(self._handle)
        else:
            # use old-style window closing protocol for non-windows platforms
            root.protocol("WM_DELETE_WINDOW", self.close)
            root.protocol("WM_DESTROY_WINDOW", self.close)
        # Save current theme and apply palette after widgets are created
        try:
            self._orig_theme_name = self._style.theme_use()
        except Exception:
            self._orig_theme_name = ''
        self.apply_theme(self._twitch.settings.dark_mode)
        self._fit_to_screen()
        # stay hidden in tray if needed, otherwise show the window when everything's ready
        if self._twitch.settings.tray and sys.platform != "darwin":
            # NOTE: this starts the tray icon thread
            self._root.after_idle(self.tray.minimize)
        else:
            self._root.after_idle(self._root.deiconify)

    # https://stackoverflow.com/questions/56329342/tkinter-treeview-background-tag-not-working
    def _fixed_map(self, option):
        # Fix for setting text colour for Tkinter 8.6.9: https://core.tcl.tk/tk/info/509cafafae
        # Returns the 'option' style map without entries starting with ('!disabled', '!selected').

        # style.map() returns an empty list for missing options, so this
        # should be future-safe.
        return [
            elm for elm in self._style.map("Treeview", query_opt=option)
            if elm[:2] != ("!disabled", "!selected")
        ]

    def wnd_proc(self, hwnd, msg, w_param, l_param):
        """
        This function serves as a message processor for all messages sent
        to the application by Windows.
        """
        if msg == win32con.WM_DESTROY:
            win32api.SetWindowLong(self._handle, win32con.GWL_WNDPROC, self.old_wnd_proc)
        if msg in self._message_map:
            return self._message_map[msg](w_param, l_param)
        return win32gui.CallWindowProc(self.old_wnd_proc, hwnd, msg, w_param, l_param)

    @cached_property
    def _handle(self) -> int:
        return int(self._root.wm_frame(), 16)

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

    def unfocus(self, event):
        # support pressing ESC to unfocus
        self._root.focus_set()
        self.channels.clear_selection()
        self.settings.clear_selection()

    # these are here to interface with underlaying GUI components
    def save(self, *, force: bool = False) -> None:
        self._cache.save(force=force)

    def grab_attention(self, *, sound: bool = True):
        self.tray.restore()
        self._root.focus_set()
        if sound:
            self._root.bell()

    def set_games(self, games: set[Game]) -> None:
        self.settings.set_games(games)

    def display_drop(
        self, drop: TimedDrop, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self.progress.display(drop, countdown=countdown, subone=subone)  # main tab
        # inventory overview is updated from within drops themselves via change events
        self.tray.update_title(drop)  # tray

    def clear_drop(self):
        self.progress.display(None)
        self.tray.update_title(None)

    def print(self, message: str):
        # print to our custom output
        self.output.print(message)

    def _set_title_bar_color(self, color: int) -> None:
        """
        Sets the Windows title bar color through DWM, and does nothing on other platforms.
        `color` is a DWM color value, such as 0x001E1E1E for dark gray.
        """
        if sys.platform != "win32":
            return
        # DWMWA_CAPTION_COLOR = 35
        DWMWA_CAPTION_COLOR = 35
        hwnd = self._root.winfo_id()
        frame_hwnd = ctypes.windll.user32.GetParent(hwnd)
        color_value = ctypes.c_int(color)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            frame_hwnd,
            DWMWA_CAPTION_COLOR,
            ctypes.byref(color_value),
            ctypes.sizeof(ctypes.c_int),
        )

    def apply_theme(self, dark: bool) -> None:
        """
        Apply dark/light palette to ttk styles and Tk widgets in a minimal, non-invasive way.
        """
        # Palette
        if dark:
            # Switch to a configurable ttk theme for better color control
            if sys.platform != "darwin" and self._style.theme_use() != "clam":
                self._style.theme_use("clam")
            bg = "#1e1e1e"
            fg = "#e6e6e6"
            sel_bg = "#094771"
            sel_fg = "#ffffff"
            link = "#4ea3ff"
            surface = "#252525"
            header = "#2a2a2a"
            fieldbg = "#2b2b2b"
            border = "#3c3c3c"
            muted = "#b3b3b3"
            accent = "#0d99ff"
        else:
            # Restore original theme if we changed it
            if getattr(self, "_orig_theme_name", '') and self._style.theme_use() == "clam":
                self._style.theme_use(self._orig_theme_name)
            # Use platform defaults but ensure toggling back is readable
            bg = "#f0f0f0"
            fg = "#000000"
            sel_bg = "#cce5ff"
            sel_fg = "#000000"
            link = "blue"
            surface = "#ffffff"
            header = "#eeeeee"
            fieldbg = "#ffffff"
            border = "#cccccc"
            muted = "#404040"
            accent = "#0a84ff"

        # Setting theme for macOS
        if sys.platform == "darwin":
            app = AppKit.NSApplication.sharedApplication()
            if dark:
                appearance = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua)
            else:
                appearance = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua)
            app.setAppearance_(appearance)

        s = self._style
        # Fonts
        default_font = nametofont("TkDefaultFont")
        self._fonts["default"] = default_font
        # Font - button style with a larger font
        self._fonts["large"] = default_font.copy()
        self._fonts["large"].config(size=10)
        s.configure("Large.TButton", font=self._fonts["large"])
        # Font - button style for sorting arrows
        self._fonts["arrow"] = default_font.copy()
        self._fonts["arrow"].config(size=16)
        s.configure("Arrow.TButton", font=self._fonts["arrow"])
        s.configure("Arrow.TButton", padding=-4)  # reduce padding on arrow buttons
        # Font - label style that mimics links
        self._fonts["underlined"] = default_font.copy()
        self._fonts["underlined"].config(underline=True)
        s.configure("Link.TLabel", font=self._fonts["underlined"], foreground=link)
        # Font - label style with a monospace font
        self._fonts["monospaced"] = default_font.copy()
        self._fonts["monospaced"].config(family="Courier New", size=10)
        s.configure("MS.TLabel", font=self._fonts["monospaced"])

        # Base containers and labels
        s.configure("TFrame", background=bg, foreground=fg)
        s.configure("TLabel", background=bg, foreground=fg)
        s.configure("TLabelframe", background=bg, foreground=fg)
        s.configure("TLabelframe.Label", background=bg, foreground=fg)
        # Buttons and checks
        s.configure("TButton", background=surface, foreground=fg, bordercolor=border)
        s.map(
            "TButton",
            background=[("active", header), ("pressed", border)],
            foreground=[("disabled", muted)],
        )
        s.configure(
            "TCheckbutton",
            background=bg,
            foreground=fg,
            focuscolor=bg,
            bordercolor=border,
        )
        s.map(
            "TCheckbutton",
            # Remove hover visuals by mapping active/pressed to the base background
            background=[
                ("active", bg),
                ("pressed", bg),
            ],
            foreground=[("disabled", muted)],
            indicatorcolor=[
                ("selected", accent if dark else fg),
                ("!selected", border),
            ],
        )
        # Notebook
        s.configure("TNotebook", background=bg, bordercolor=border)
        s.configure("TNotebook.Tab", background=surface, foreground=fg, bordercolor=border)
        s.map(
            "TNotebook.Tab",
            background=[("selected", header), ("active", header)],
            foreground=[("disabled", muted)],
        )
        # Entries/Combos
        s.configure(
            "TEntry", fieldbackground=fieldbg, background=fieldbg, foreground=fg, insertcolor=fg
        )
        s.configure(
            "TCombobox", fieldbackground=fieldbg, background=fieldbg, foreground=fg, arrowcolor=fg
        )
        # Ensure readability for readonly comboboxes (Language, Priority mode)
        s.map(
            "TCombobox",
            foreground=[("readonly", fg), ("disabled", muted)],
            fieldbackground=[("readonly", fieldbg)],
            background=[("readonly", fieldbg)],
            arrowcolor=[("readonly", fg)],
        )
        s.map("TEntry", foreground=[("disabled", muted)])
        # Treeview
        s.configure(
            "Treeview",
            background=surface,
            fieldbackground=surface,
            foreground=fg,
            bordercolor=border,
        )
        s.map(
            "Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        s.configure("Treeview.Heading", background=header, foreground=fg, bordercolor=border)
        # Progressbar
        s.configure("TProgressbar", background=accent, troughcolor=surface)
        # Scrollbars
        s.configure(
            "Vertical.TScrollbar",
            background=surface,
            troughcolor=bg,
            arrowcolor=fg,
            bordercolor=border,
        )
        s.configure(
            "Horizontal.TScrollbar",
            background=surface,
            troughcolor=bg,
            arrowcolor=fg,
            bordercolor=border,
        )

        # Pure Tk widgets
        # Console text
        self.output.configure_theme(bg=surface, fg=fg, sel_bg=sel_bg, sel_fg=sel_fg)
        # Listboxes
        self.settings._priority_list.configure_theme(
            bg=surface, fg=fg, sel_bg=sel_bg, sel_fg=sel_fg
        )
        self.settings._exclude_list.configure_theme(
            bg=surface, fg=fg, sel_bg=sel_bg, sel_fg=sel_fg
        )
        self.settings._detected_list.configure_theme(
            bg=surface, fg=fg, sel_bg=sel_bg, sel_fg=sel_fg
        )
        self.settings._game_dirs_list.configure_theme(
            bg=surface, fg=fg, sel_bg=sel_bg, sel_fg=sel_fg
        )
        # Inventory and Settings canvases
        self.inv._area.configure_theme(bg=bg)
        self.settings._area.configure_theme(bg=bg)

        # Tk option database for selection/popup list readability (affects Tk-backed widgets)
        # Global selection colors and listbox defaults (covers Combobox dropdown)
        self._root.option_add("*selectBackground", sel_bg)
        self._root.option_add("*selectForeground", sel_fg)
        # Combobox dropdown list (Tk Listbox)
        for key in (
            "*TCombobox*Listbox.background",
            "*TCombobox*Listbox.Background",
            "*Listbox.background",
        ):
            self._root.option_add(key, surface)
        for key in (
            "*TCombobox*Listbox.foreground",
            "*TCombobox*Listbox.Foreground",
            "*Listbox.foreground",
        ):
            self._root.option_add(key, fg)
        for key in (
            "*TCombobox*Listbox.selectBackground",
            "*Listbox.selectBackground",
        ):
            self._root.option_add(key, sel_bg)
        for key in (
            "*TCombobox*Listbox.selectForeground",
            "*Listbox.selectForeground",
        ):
            self._root.option_add(key, sel_fg)

        # Set Windows title bar color to match dark theme
        if dark:
            # Use dark gray color 0x001E1E1E (ARGB format, matches bg color #1e1e1e)
            self._set_title_bar_color(0x001E1E1E)
        else:
            # Reset to system default title bar color
            self._set_title_bar_color(0xFFFFFFFF)
        # the theme sets the fonts and paddings, so the minimum window size follows it
        self._minimum.measure()

    def _fit_to_screen(self) -> None:
        """Shrink the window to the largest size Tk allows on the screen, when it requests more."""
        root = self._root
        root.update_idletasks()
        wanted = Size(root.winfo_reqwidth(), root.winfo_reqheight())
        size = fitted_size(wanted, Size(*root.minsize()), Size(*root.maxsize()))
        if size != wanted:
            root.geometry(f"{size.width}x{size.height}")


###################
# GUI MANAGER END #
###################


if __name__ == "__main__":
    # Everything below is for debug purposes only
    from types import SimpleNamespace
    from contextlib import asynccontextmanager

    class StrNamespace(SimpleNamespace):
        __hash__ = object.__hash__  # type: ignore

        def __str__(self):
            if hasattr(self, "_str__"):
                return self._str__(self)
            return super().__str__()

    class HashNamespace(SimpleNamespace):
        __hash__ = object.__hash__  # type: ignore

    def create_game(id: int, name: str):
        return StrNamespace(name=name, id=id, _str__=lambda s: s.name)

    iid = 0

    def create_channel(
        name: str,
        status: int,
        game: str | None,
        drops: bool,
        viewers: int,
        acl_based: bool,
    ):
        # status: 0 -> OFFLINE, 1 -> PENDING_ONLINE, 2 -> ONLINE
        if status == 1:
            status = False
            pending = True
        else:
            pending = False
        if game is not None:
            game_obj: StrNamespace | None = create_game(0, game)
        else:
            game_obj = None
        global iid
        return SimpleNamespace(
            name=name,
            iid=(iid := iid + 1),
            online=bool(status),
            pending_online=pending,
            game=game_obj,
            drops_enabled=drops,
            viewers=viewers,
            acl_based=acl_based,
        )

    def create_drop(
        campaign_name: str,
        game_name: str,
        rewards: list[str],
        claimed_drops: int,
        total_drops: int,
        current_minutes: int,
        total_minutes: int,
    ):
        cd = claimed_drops
        td = total_drops
        cm = current_minutes
        tm = total_minutes
        ref_stamp = datetime.now(timezone.utc)
        drop_image_url = (
            "https://static-cdn.jtvnw.net/twitch-quests-assets/"
            "REWARD/e0ede26e-b071-47f0-af5f-b80b26fa9fb4.png"
        )
        campaign_image_url = "https://static-cdn.jtvnw.net/ttv-boxart/515025-120x160.jpg"
        benefits = [SimpleNamespace(name=name, image_url=drop_image_url) for name in rewards]
        mock = SimpleNamespace(
            id="0",
            campaign=HashNamespace(
                name=campaign_name,
                id="campaign",
                game=create_game(0, game_name),
                expired=False,
                active=True,
                upcoming=False,
                eligible=True,
                finished=False,
                link_url="https://google.com",
                image_url=campaign_image_url,
                allowed_channels=[],
                starts_at=ref_stamp,
                ends_at=ref_stamp + timedelta(days=7),
                timed_drops={},
                claimed_drops=cd,
                total_drops=td,
                required_minutes=tm,
                remaining_drops=td - cd,
                progress=(cd * tm + cm) / (td * tm),
                remaining_minutes=(td - cd) * tm - cm,
            ),
            image_url=drop_image_url,
            can_claim=False,
            can_earn=lambda: False,
            is_claimed=False,
            preconditions=True,
            benefits=benefits,
            rewards_text=lambda: ', '.join(b.name for b in benefits),
            starts_at=ref_stamp + timedelta(seconds=2),
            ends_at=ref_stamp + timedelta(days=7) - timedelta(seconds=2),
            progress=cm/tm,
            current_minutes=cm,
            required_minutes=tm,
            remaining_minutes=tm-cm,
        )
        mock.campaign.timed_drops["0"] = mock
        mock.campaign.drops = mock.campaign.timed_drops.values()
        return mock

    async def read_icon() -> bytes:
        return resource_path("icons/pickaxe.ico").read_bytes()

    @asynccontextmanager
    async def icon_request(method: str, url: str):
        # every image of the mock is the app icon, so the preview sends no request
        yield SimpleNamespace(status=200, read=read_icon)

    async def main(exit_event: asyncio.Event):
        # Initialize GUI debug
        mock = SimpleNamespace(
            settings=SimpleNamespace(
                tray=False,
                priority=["Best Game", "My Game*"],
                proxy=URL(),
                dark_mode=False,
                alter=lambda: None,
                language="English",
                autostart_tray=False,
                exclude={"Lit Game"},
                refresh_interval=5,
                restart_delay=10,
                game_dirs=["/home/user/.local/share/Steam", "/home/user/Games/Heroic"],
                detected_games=["Cleaning Masters", "Lit Game"],
                tray_notifications=True,
                enable_badges_emotes=False,
                available_drops_check=False,
                logging_level=LOGGING_LEVELS[0],
                priority_mode=PriorityMode.PRIORITY_ONLY,
            )
        )
        mock.change_state = lambda state: mock.gui.print(f"State change: {state.value}")
        mock.state_change = lambda state: partial(mock.change_state, state)
        mock.request = icon_request
        # _.set_language("Русский")
        gui = GUIManager(mock)  # type: ignore
        mock.gui = gui
        mock.close = gui.stop
        gui.start()
        assert gui._poll_task is not None
        gui._poll_task.add_done_callback(lambda t: exit_event.set())
        # Login form
        gui.login.update("Login required", None)
        # Game selector and settings panel games
        gui.set_games(set([
            create_game(420690, "Lit Game"),
            create_game(123456, "Best Game"),
            create_game(654321, "My Game Very Long Name"),
        ]))
        gui.settings.set_wanted_games([
            create_game(123456, "Best Game"),
            create_game(654321, "My Game Very Long Name"),
            create_game(0, "Cleaning Masters"),
        ])
        # Channel list
        gui.channels.display(
            create_channel(
                name="Thomus",
                status=0,
                game=None,
                drops=False,
                viewers=0,
                acl_based=True,
            ),
            add=True,
        )
        channel = create_channel(
            name="Traitus", status=1, game=None, drops=False, viewers=0, acl_based=True
        )
        gui.channels.display(channel, add=True)
        gui.channels.set_watching(channel)
        gui.channels.display(
            create_channel(
                name="Testus",
                status=2,
                game="Best Game",
                drops=True,
                viewers=42,
                acl_based=False,
            ),
            add=True,
        )
        gui.channels.display(
            create_channel(
                name="Livus",
                status=2,
                game="Best Game",
                drops=True,
                viewers=69,
                acl_based=False,
            ),
            add=True,
        )
        gui._root.update()
        gui.channels.get_selection()
        # Inventory overview
        drop = create_drop(
            "Wardrobe Cleaning", "Cleaning Masters", ["Fancy Pants"], 2, 7, 0, 240
        )
        campaign = drop.campaign
        await gui.inv.add_campaign(campaign)

        gui.print("Single-line test message")
        await asyncio.sleep(1)
        gui.print("Multi-line\ntest\nmessage")

        # Tray
        # gui.tray.minimize()
        await asyncio.sleep(2)
        claim_text = (
            f"{campaign.game.name}\n"
            f"{drop.rewards_text()} ({campaign.claimed_drops}/{campaign.total_drops})"
        )
        gui.tray.notify(claim_text, "Mined Drop")

        # Drop progress
        gui.display_drop(drop, countdown=False)
        await asyncio.sleep(3)

        gui.progress.start_timer()
        await asyncio.sleep(5)

        gui.clear_drop()
        await asyncio.sleep(5)

        campaign.can_earn = lambda: True
        gui.inv.update_drop(drop)
        gui.display_drop(drop)
        await asyncio.sleep(10)

        drop.current_minutes = 239
        drop.remaining_minutes = 1
        drop.progress = 239/240
        campaign.remaining_minutes -= 1
        gui.inv.update_drop(drop)
        gui.display_drop(drop)
        await asyncio.sleep(63)

        drop.current_minutes = 240
        drop.remaining_minutes = 0
        drop.progress = 1.0
        campaign.remaining_minutes -= 1
        campaign.progress = 3/7
        campaign.claimed_drops = 3
        campaign.remaining_drops = 4
        gui.inv.update_drop(drop)
        gui.display_drop(drop)

    def main_exit(task: asyncio.Task[None]) -> None:
        if task.exception() is not None:
            exit_event.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    exit_event = asyncio.Event()
    main_task = loop.create_task(main(exit_event))
    main_task.add_done_callback(main_exit)
    loop.run_until_complete(exit_event.wait())
    if main_task.done():
        loop.run_until_complete(main_task)
