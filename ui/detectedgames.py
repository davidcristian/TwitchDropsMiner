"""The mixin of `SettingsPanel` with the Detected Games section: the games of the last scan and the game folders."""
from __future__ import annotations

from pathlib import Path
from collections import abc
from tkinter import ttk
from typing import TYPE_CHECKING

from translate import _
from gamelib import GameMatch, MatchKind
from folderpicker import FolderPicker
from utils import start_task, task_wrapper

from .widgets import PaddedListbox

if TYPE_CHECKING:
    from gui import GUIManager
    from settings import Settings


class DetectedGamesMixin:
    """The methods of `SettingsPanel` that build the Detected Games section, fill it and change the game folders."""

    _manager: GUIManager
    _settings: Settings
    _folder_picker: FolderPicker
    _detected_list: PaddedListbox
    _detected_label: ttk.Label
    _game_dirs_list: PaddedListbox
    _game_dir_add_button: ttk.Button

    def _build_detect_frame(self, center_frame: ttk.Frame) -> None:
        """Build the Detected Games list, the game folders with their buttons, and Rescan."""
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
