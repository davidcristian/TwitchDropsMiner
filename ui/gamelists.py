"""The mixin of `SettingsPanel` with the Priority and Exclude lists and the games that a wildcard entry matches."""
from __future__ import annotations

from functools import partial
from tkinter import ttk
from typing import TYPE_CHECKING

from translate import _
from gamelib import has_wildcard, matching_names, compile_pattern
from utils import Game
from constants import MAX_INT

from .placeholder import PlaceholderCombobox
from .widgets import PaddedListbox

if TYPE_CHECKING:
    from gui import GUIManager
    from settings import Settings


class GameListsMixin:
    """The methods of `SettingsPanel` that build the Priority and Exclude lists and add, move and remove entries."""

    _manager: GUIManager
    _settings: Settings
    _game_names: set[str]
    _priority_entry: PlaceholderCombobox
    _priority_list: PaddedListbox
    _exclude_entry: PlaceholderCombobox
    _exclude_list: PaddedListbox

    def _build_priority_frame(self, center_frame: ttk.Frame) -> None:
        """Build the Priority list with its game name field and its add, move and delete buttons."""
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

    def _build_exclude_frame(self, center_frame: ttk.Frame) -> None:
        """Build the Exclude list, in alphabetical order, with its game name field and its add and delete buttons."""
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
