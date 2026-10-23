"""`SettingsPanel`, the Settings tab: its sections in a scroll area, the Games Being Mined table and Reload."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from collections import abc
from functools import cached_property
from tkinter import ttk, StringVar, IntVar
from typing import TypedDict, TYPE_CHECKING

from translate import _
from autostart import AutostartEntry, autostart_entry
from gamelib import match_rank, compile_patterns
from folderpicker import FolderPicker
from scrollarea import ScrollArea
from settings import default_settings, setting_choices
from utils import Game
from constants import State, PriorityMode

from .generalsettings import GeneralSettingsMixin
from .gamelists import GameListsMixin
from .detectedgames import DetectedGamesMixin

if TYPE_CHECKING:
    from gui import GUIManager
    from settings import Settings


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


class SettingsPanel(GeneralSettingsMixin, GameListsMixin, DetectedGamesMixin):
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
        self._build_wanted_frame(center_frame)
        self._build_general_frame(center_frame)
        self._build_advanced_frame(center_frame)
        self._build_priority_frame(center_frame)
        self._build_exclude_frame(center_frame)
        self._build_detect_frame(center_frame)
        self._build_reload_frame(center_frame)

    def _build_wanted_frame(self, center_frame: ttk.Frame) -> None:
        """Build the Games Being Mined table across the top, which `set_wanted_games` fills."""
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

    def _build_reload_frame(self, center_frame: ttk.Frame) -> None:
        """Build the row under the sections with the Reload button."""
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
