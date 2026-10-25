from __future__ import annotations

import sys
import ctypes
import asyncio
import logging
from tkinter.font import Font
from functools import cached_property
from tkinter import Tk, ttk
from typing import NoReturn, TYPE_CHECKING

if sys.platform == "win32":
    import win32api
    import win32con
    import win32gui

from translate import _
from cache import ImageCache
from colorfonts import LoadedFontLibraries, skip_color_fonts
from scrollarea import MinimumSize, Size, fitted_size
from utils import resource_path, set_root_icon, Game
from constants import WINDOW_TITLE, OUTPUT_FORMATTER
from ui import (
    HelpTab,
    Notebook,
    TrayIcon,
    StatusBar,
    LoginForm,
    ThemeMixin,
    ChannelList,
    ConsoleOutput,
    SettingsPanel,
    EventLoopMixin,
    WebsocketStatus,
    CampaignProgress,
    InventoryOverview,
    _TKOutputHandler,
    run_preview,
)

if TYPE_CHECKING:
    from tkinter import Event, Misc

    from twitch import Twitch
    from inventory import TimedDrop


def sizes_again_after_first_map(windowing_system: str) -> bool:
    """Return whether the minimum size is measured and the window fitted to the screen again after it first shows."""
    # macOS shows a window fitted while withdrawn as zoomed, and makes it 20 pixels smaller when it first shows.
    # On macOS with Python 3.14.9 in CI, the content requested 8 pixels less on each axis after __init__ than during it.
    return windowing_system == "aqua"


class GUIManager(EventLoopMixin, ThemeMixin):
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
        if sizes_again_after_first_map(root.tk.call("tk", "windowingsystem")):
            self._first_map = root.bind("<Map>", self._size_again_after_first_map)
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

    def _fit_to_screen(self) -> None:
        """Shrink the window to the largest size Tk allows on the screen, when it requests more."""
        root = self._root
        root.update_idletasks()
        wanted = Size(root.winfo_reqwidth(), root.winfo_reqheight())
        size = fitted_size(wanted, Size(*root.minsize()), Size(*root.maxsize()))
        if size != wanted:
            root.geometry(f"{size.width}x{size.height}")

    def _size_again_after_first_map(self, event: Event[Misc]) -> None:
        # a fit inside the first <Map> handler still leaves the window smaller on macOS, and one after it does not
        if event.widget is self._root:
            self._root.unbind("<Map>", self._first_map)
            self._root.after_idle(self._measure_and_fit)

    def _measure_and_fit(self) -> None:
        self._minimum.measure()
        self._fit_to_screen()


if __name__ == "__main__":
    run_preview(GUIManager)
