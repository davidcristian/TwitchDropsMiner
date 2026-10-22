"""Imports pystray with the first tray backend that loads, and makes the icon of its X11 backend receive clicks."""
from __future__ import annotations

import logging
import traceback
from collections import abc
from types import ModuleType
from typing import Protocol


logger = logging.getLogger("TwitchDrops")

BACKEND_VARIABLE = "PYSTRAY_BACKEND"
# pystray's own order outside Windows and macOS. pystray moves on only after an ImportError, but a GTK library
# that fails to load makes PyGObject raise ValueError or AssertionError.
BACKENDS = ("appindicator", "gtk", "xorg")
BACKEND_ERRORS = (ImportError, ValueError, AssertionError)
XORG_MODULE = "pystray._xorg"
# the X11 protocol's ButtonPressMask, which is Xlib.X.ButtonPressMask
BUTTON_PRESS_MASK = 1 << 2


class WindowAttributes(Protocol):
    """The reply of `IconWindow.get_attributes`, with the events that the X server sends to this client."""

    your_event_mask: int


class IconWindow(Protocol):
    """The calls of an Xlib window that read and set the events which the X server sends to this client."""

    def get_attributes(self) -> WindowAttributes: ...

    def change_attributes(self, *, event_mask: int) -> object: ...


def load_pystray() -> ModuleType:
    """Import pystray, which chooses its tray backend from PYSTRAY_BACKEND as it loads."""
    # an import statement, not importlib, so that PyInstaller finds pystray and bundles it
    import pystray

    return pystray


def session_bus_error() -> str | None:
    """Return why a connection to the DBus session bus fails, or None when it opens or PyGObject does not load."""
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except BACKEND_ERRORS:
        return None
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as error:
        return str(error.message)
    return None


def icon_class(base: type) -> type:
    """Return base, or a subclass whose window receives clicks when base is the Icon class of pystray's xorg backend."""
    if base.__module__ != XORG_MODULE:
        return base

    class ClickableIcon(base):
        # pystray's xorg icon runs its default menu item on a left click, but creates its window without
        # ButtonPressMask, so the X server does not send the click to pystray.
        def _create_window(self) -> IconWindow:
            window: IconWindow = super()._create_window()
            window.change_attributes(event_mask=window.get_attributes().your_event_mask | BUTTON_PRESS_MASK)
            return window

    return ClickableIcon


def _describe(error: BaseException) -> str:
    """Return the last line that a traceback of the error shows, such as `ValueError: Namespace Gtk not available`."""
    return traceback.format_exception_only(type(error), error)[-1].strip()


def import_pystray(
    load: abc.Callable[[], ModuleType],
    environ: abc.MutableMapping[str, str],
    platform: str,
    bus_error: abc.Callable[[], str | None],
) -> ModuleType:
    """Return pystray from load, with the first of BACKENDS that loads unless the platform or environ chooses one.

    environ holds PYSTRAY_BACKEND, platform is a `sys.platform` value, and bus_error works like `session_bus_error`.
    """
    if platform in ("win32", "darwin") or environ.get(BACKEND_VARIABLE):
        return load()
    backends = BACKENDS
    # The appindicator and gtk icons connect to the bus in their thread before they mark the icon ready. Without
    # a bus, pystray's setup thread waits for that mark forever, and Python waits for that thread at exit.
    if (reason := bus_error()) is not None:
        logger.warning(
            f"Tray icon: the app cannot connect to the DBus session bus ({reason}), "
            f"which the appindicator and gtk backends need, so it uses the xorg backend"
        )
        backends = BACKENDS[-1:]
    previous = environ.get(BACKEND_VARIABLE)
    try:
        for backend, following in zip(backends, backends[1:]):
            environ[BACKEND_VARIABLE] = backend
            try:
                return load()
            except BACKEND_ERRORS as error:
                logger.warning(
                    f"Tray icon: the {backend} backend failed to load ({_describe(error)}), "
                    f"so the app tries the {following} backend"
                )
        environ[BACKEND_VARIABLE] = backends[-1]
        return load()
    finally:
        if previous is None:
            del environ[BACKEND_VARIABLE]
        else:
            environ[BACKEND_VARIABLE] = previous
