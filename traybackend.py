"""Imports pystray with the first tray backend that loads, and fixes how its X11 icon docks, hides and gets clicks."""
from __future__ import annotations

import logging
import threading
import traceback
from collections import abc
from types import ModuleType, SimpleNamespace
from typing import Protocol


logger = logging.getLogger("TwitchDrops")

BACKEND_VARIABLE = "PYSTRAY_BACKEND"
# pystray's own order outside Windows and macOS. pystray moves on only after an ImportError, but a GTK library
# that fails to load makes PyGObject raise ValueError or AssertionError.
BACKENDS = ("appindicator", "gtk", "xorg")
BACKEND_ERRORS = (ImportError, ValueError, AssertionError)
XORG_MODULE = "pystray._xorg"
# the X11 protocol's ButtonPressMask, StructureNotifyMask and ClientMessage event type, which Xlib.X names so
BUTTON_PRESS_MASK = 1 << 2
STRUCTURE_NOTIFY_MASK = 1 << 17
CLIENT_MESSAGE = 33


class WindowAttributes(Protocol):
    """The reply of `IconWindow.get_attributes`, with the events that the X server sends to this client."""

    your_event_mask: int


class IconWindow(Protocol):
    """The calls of an Xlib window that read and set the events which the X server sends to this client."""

    def get_attributes(self) -> WindowAttributes: ...

    def change_attributes(self, *, event_mask: int) -> object: ...


class ClientMessage(Protocol):
    """An Xlib ClientMessage event: the atom that names its type, and its format with its five numbers."""

    client_type: int
    data: tuple[int, abc.Sequence[int]]


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
    """Return base, or a subclass that fixes docking, hiding and clicks when base is pystray's xorg Icon class."""
    if base.__module__ != XORG_MODULE:
        return base

    class XorgIcon(base):
        # pystray docks the icon only as it starts or shows it. A tray that starts later, as tint2 does 15 seconds
        # after its own start without a window manager, announces itself with a MANAGER message to the root window.
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self._display.screen().root.change_attributes(event_mask=STRUCTURE_NOTIFY_MASK)
            self._manager_atom = self._display.intern_atom("MANAGER")
            pystray_handler = self._message_handlers[CLIENT_MESSAGE]
            self._message_handlers[CLIENT_MESSAGE] = lambda event: self._on_client_message(event, pystray_handler)

        def _on_client_message(
            self, event: ClientMessage, pystray_handler: abc.Callable[[ClientMessage], None]
        ) -> None:
            if event.client_type != self._manager_atom:
                pystray_handler(event)
            elif event.data[1][1] == self._net_system_tray_sx and self._systray_manager is None:
                # docks the icon and draws its image
                self._update_icon()

        # python-xlib 0.33 can leave a thread that waits for a reply waiting forever when another thread sends a
        # request on the same connection, so a message from another thread goes through a new connection.
        def _send_message(self, window: object, client_type: int, *data: int) -> None:
            if threading.current_thread().ident == self._thread.ident:
                super()._send_message(window, client_type, *data)
                return
            # pystray's _send_message reads only the _display of the icon that it is given
            connection = type(self._display)()
            try:
                base._send_message(SimpleNamespace(_display=connection), window, client_type, *data)
                # Xvfb dropped the message when the connection closed right after it
                connection.sync()
            finally:
                connection.close()

        # pystray's xorg icon runs its default menu item on a left click, but creates its window without
        # ButtonPressMask, so the X server does not send the click to pystray.
        def _create_window(self) -> IconWindow:
            window: IconWindow = super()._create_window()
            window.change_attributes(event_mask=window.get_attributes().your_event_mask | BUTTON_PRESS_MASK)
            return window

        # pystray hides the icon by unmapping its window and moving it out of the tray, and stalonetray then maps
        # that window on the screen. A clear XEmbed mapped flag makes the tray hide the icon instead.
        def _hide(self) -> None:
            self._set_mapped_flag(False)

        def _show(self) -> None:
            self._set_mapped_flag(True)
            # a second dock request for a docked window makes trayer embed it again, and often leave it out
            if self._systray_manager is None:
                super()._show()

        def _set_mapped_flag(self, mapped: bool) -> None:
            flags = self._XEMBED_MAPPED if mapped else 0
            self._window.change_property(self._xembed_info, self._xembed_info, 32, [self._XEMBED_VERSION, flags])
            self._display.flush()

    return XorgIcon


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
