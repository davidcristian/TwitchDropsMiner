"""The mixin of `GUIManager` with the light and dark themes and the color of the Windows title bar."""
from __future__ import annotations

import sys
import ctypes
from tkinter.font import Font, nametofont
from typing import TYPE_CHECKING

if sys.platform == "darwin":
    import AppKit

if TYPE_CHECKING:
    from tkinter import Tk, ttk

    from scrollarea import MinimumSize
    from .output import ConsoleOutput
    from .inventorytab import InventoryOverview
    from .settingstab import SettingsPanel


class ThemeMixin:
    """The methods of `GUIManager` that set the colors and fonts of every widget for the light or dark theme."""

    _root: Tk
    _style: ttk.Style
    _fonts: dict[str, Font]
    _orig_theme_name: str
    _minimum: MinimumSize
    output: ConsoleOutput
    inv: InventoryOverview
    settings: SettingsPanel

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
