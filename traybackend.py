"""Imports pystray with the first tray backend that loads, so a broken GTK library leaves the X11 backend."""
from __future__ import annotations

import logging
import traceback
from collections import abc
from types import ModuleType


logger = logging.getLogger("TwitchDrops")

BACKEND_VARIABLE = "PYSTRAY_BACKEND"
# pystray's own order outside Windows and macOS. pystray moves on only after an ImportError, but a GTK library
# that fails to load makes PyGObject raise ValueError or AssertionError.
BACKENDS = ("appindicator", "gtk", "xorg")
BACKEND_ERRORS = (ImportError, ValueError, AssertionError)


def load_pystray() -> ModuleType:
    """Import pystray, which chooses its tray backend from PYSTRAY_BACKEND as it loads."""
    # an import statement, not importlib, so that PyInstaller finds pystray and bundles it
    import pystray

    return pystray


def _describe(error: BaseException) -> str:
    """Return the last line that a traceback of the error shows, such as `ValueError: Namespace Gtk not available`."""
    return traceback.format_exception_only(type(error), error)[-1].strip()


def import_pystray(
    load: abc.Callable[[], ModuleType], environ: abc.MutableMapping[str, str], platform: str
) -> ModuleType:
    """Return pystray from load, with the first of BACKENDS that loads unless the platform or environ chooses one.

    environ is the environment that pystray reads PYSTRAY_BACKEND from, and platform is a `sys.platform` value.
    """
    if platform in ("win32", "darwin") or environ.get(BACKEND_VARIABLE):
        return load()
    previous = environ.get(BACKEND_VARIABLE)
    try:
        for backend, following in zip(BACKENDS, BACKENDS[1:]):
            environ[BACKEND_VARIABLE] = backend
            try:
                return load()
            except BACKEND_ERRORS as error:
                logger.warning(
                    f"Tray icon: the {backend} backend failed to load ({_describe(error)}), "
                    f"so the app tries the {following} backend"
                )
        environ[BACKEND_VARIABLE] = BACKENDS[-1]
        return load()
    finally:
        if previous is None:
            del environ[BACKEND_VARIABLE]
        else:
            environ[BACKEND_VARIABLE] = previous
