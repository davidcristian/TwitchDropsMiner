"""The mixin of `SettingsPanel` with the General and Advanced sections, the autostart entry and the proxy check."""
from __future__ import annotations

import sys
import logging
import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import TYPE_CHECKING

from yarl import URL

from translate import _, default_translation
from autostart import AutostartEntry, autostart_command, source_python
from constants import SELF_PATH, IS_PACKAGED, SCRIPTS_PATH, PriorityMode

from .placeholder import PlaceholderEntry
from .widgets import SelectCombobox

if TYPE_CHECKING:
    from gui import GUIManager
    from settings import Settings
    from .settingstab import _SettingsVars


logger = logging.getLogger("TwitchDrops")


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


class GeneralSettingsMixin:
    """The methods of `SettingsPanel` that build the General and Advanced sections and store their changes."""

    _manager: GUIManager
    _settings: Settings
    _autostart: AutostartEntry
    _vars: _SettingsVars
    _proxy: PlaceholderEntry
    PRIORITY_MODES: dict[PriorityMode, str]
    REFRESH_INTERVALS: dict[int, str]
    RESTART_DELAYS: dict[int, str]

    def _build_general_frame(self, center_frame: ttk.Frame) -> None:
        """Build the General section: the language, the checkboxes, the drop-down lists and the proxy."""
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

    def _build_advanced_frame(self, center_frame: ttk.Frame) -> None:
        """Build the Advanced section: the warning and the two checkboxes under it."""
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
