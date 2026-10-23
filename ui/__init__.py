"""The parts of the window that `gui.py` builds: the generic widgets, the panels and the tabs."""
from __future__ import annotations

from .placeholder import PlaceholderCombobox, PlaceholderEntry
from .widgets import LinkLabel, MouseOverLabel, Notebook, PaddedListbox, SelectCombobox

__all__ = [
    "LinkLabel",
    "MouseOverLabel",
    "Notebook",
    "PaddedListbox",
    "PlaceholderCombobox",
    "PlaceholderEntry",
    "SelectCombobox",
]
