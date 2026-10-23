"""The parts of the window that `gui.py` builds: the generic widgets, the panels and the tabs."""
from __future__ import annotations

from .placeholder import PlaceholderCombobox, PlaceholderEntry
from .widgets import LinkLabel, MouseOverLabel, Notebook, PaddedListbox, SelectCombobox
from .status import StatusBar, WebsocketStatus
from .login import LoginForm
from .progress import CampaignProgress
from .output import ConsoleOutput, _TKOutputHandler
from .channellist import ChannelList
from .tray import TrayIcon
from .inventorytab import InventoryOverview
from .helptab import HelpTab
from .settingstab import SettingsPanel
from .preview import run_preview

__all__ = [
    "CampaignProgress",
    "ChannelList",
    "ConsoleOutput",
    "HelpTab",
    "InventoryOverview",
    "LinkLabel",
    "LoginForm",
    "MouseOverLabel",
    "Notebook",
    "PaddedListbox",
    "PlaceholderCombobox",
    "PlaceholderEntry",
    "SelectCombobox",
    "SettingsPanel",
    "StatusBar",
    "TrayIcon",
    "WebsocketStatus",
    "_TKOutputHandler",
    "run_preview",
]
