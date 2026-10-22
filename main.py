from __future__ import annotations

import logging
# import an additional thing for proper PyInstaller freeze support
from multiprocessing import freeze_support
from pathlib import Path


def log_file_handler(path: Path, formatter: logging.Formatter) -> logging.FileHandler:
    """Return a handler that appends log records to the file at path in UTF-8, whatever the locale's code page."""
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(formatter)
    return handler


if __name__ == "__main__":
    freeze_support()
    import sys

    # truststore and utils.py need Python 3.10, so the check comes before they are imported
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or higher is required")

    import io
    import os
    import signal
    import asyncio
    import argparse
    import warnings
    import traceback
    import tkinter as tk
    from tkinter import messagebox
    from typing import NoReturn, TYPE_CHECKING

    from parentexit import LinuxProcess, end_with_runtime
    end_with_runtime(sys.platform, os.environ, LinuxProcess())

    import truststore
    truststore.inject_into_ssl()

    from translate import _, save_template
    from twitch import Twitch
    from settings import Settings
    from version import __version__
    from instancelock import lock_file
    from utils import resource_path, set_root_icon
    from constants import IS_PACKAGED, LOGGING_LEVELS, SELF_PATH, FILE_FORMATTER, LOG_PATH, LOCK_PATH

    if TYPE_CHECKING:
        from _typeshed import SupportsWrite

    if not IS_PACKAGED:
        save_template()

    warnings.simplefilter("default", ResourceWarning)

    # import tracemalloc
    # tracemalloc.start(3)

    # Suppress X11 Input Method registration on Linux to prevent
    # XWayland/Mutter lockups during heavy Tkinter layout updates.
    if sys.platform.startswith("linux") and "XMODIFIERS" not in os.environ:
        os.environ["XMODIFIERS"] = "@im=none"

    class Parser(argparse.ArgumentParser):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._message: io.StringIO = io.StringIO()

        def _print_message(self, message: str, file: SupportsWrite[str] | None = None) -> None:
            self._message.write(message)
            # print(message, file=self._message)

        def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
            try:
                super().exit(status, message)  # sys.exit(2)
            finally:
                messagebox.showerror("Argument Parser Error", self._message.getvalue())

    class ParsedArgs(argparse.Namespace):
        _verbose: int
        _debug_ws: bool
        _debug_gql: bool
        log: bool
        tray: bool
        dump: bool

        # TODO: replace int with union of literal values once typeshed updates
        @property
        def logging_level(self) -> int:
            return LOGGING_LEVELS[min(self._verbose, 4)]

        @property
        def debug_ws(self) -> int:
            """
            If the debug flag is True, return DEBUG.
            If the main logging level is DEBUG, return INFO to avoid seeing raw messages.
            Otherwise, return NOTSET to inherit the global logging level.
            """
            if self._debug_ws:
                return logging.DEBUG
            elif self._verbose >= 4:
                return logging.INFO
            return logging.NOTSET

        @property
        def debug_gql(self) -> int:
            if self._debug_gql:
                return logging.DEBUG
            elif self._verbose >= 4:
                return logging.INFO
            return logging.NOTSET

    # handle input parameters
    # NOTE: parser output is shown via message box
    # we also need a dummy invisible window for the parser
    root = tk.Tk()
    root.overrideredirect(True)
    root.withdraw()
    set_root_icon(root, resource_path("icons/pickaxe.ico"))
    root.update()
    parser = Parser(
        SELF_PATH.name,
        description="A program that allows you to mine timed drops on Twitch.",
    )
    parser.add_argument("--version", action="version", version=f"v{__version__}")
    parser.add_argument("-v", dest="_verbose", action="count", default=0)
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--dump", action="store_true")
    # undocumented debug args
    parser.add_argument(
        "--debug-ws", dest="_debug_ws", action="store_true", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--debug-gql", dest="_debug_gql", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args(namespace=ParsedArgs())
    # load settings
    try:
        settings = Settings(args)
    except Exception:
        messagebox.showerror(
            "Settings error",
            f"There was an error while loading the settings file:\n\n{traceback.format_exc()}"
        )
        sys.exit(4)
    try:
        _.set_language(settings.language)
    except ValueError:
        # this language doesn't exist - stick to English
        pass
    lock = lock_file(LOCK_PATH)
    if lock.error is not None:
        messagebox.showerror(
            _("error", "cannot_start"), _("error", "folder_not_writable").format(error=lock.error)
        )
        sys.exit(5)
    if lock.file is None:
        # another copy of the app runs from this folder
        sys.exit(3)
    # dummy window isn't needed anymore
    root.destroy()
    # get rid of unneeded objects
    del root, parser

    # client run
    async def main():
        # handle logging stuff
        if settings.logging_level > logging.DEBUG:
            # redirect the root logger into a NullHandler, effectively ignoring all logging calls
            # that aren't ours. This always runs, unless the main logging level is DEBUG or lower.
            logging.getLogger().addHandler(logging.NullHandler())
        logger = logging.getLogger("TwitchDrops")
        logger.setLevel(settings.logging_level)
        if settings.log:
            logger.addHandler(log_file_handler(LOG_PATH, FILE_FORMATTER))
        logging.getLogger("TwitchDrops.gql").setLevel(settings.debug_gql)
        logging.getLogger("TwitchDrops.websocket").setLevel(settings.debug_ws)

        exit_status = 0
        client = Twitch(settings)
        loop = asyncio.get_running_loop()
        if sys.platform == "linux":
            loop.add_signal_handler(signal.SIGINT, lambda *_: client.gui.close())
            loop.add_signal_handler(signal.SIGTERM, lambda *_: client.gui.close())
        try:
            await client.run()
        except Exception:
            exit_status = 1
            client.prevent_close()
            client.print(_("status", "fatal_error"))
            client.print(traceback.format_exc())
        finally:
            if sys.platform == "linux":
                # SIGTERM stays handled until the loop closes, so a second one, such as the one parentexit.py has
                # the kernel send, cannot end the app before it saves its files
                loop.remove_signal_handler(signal.SIGINT)
            client.print(_("gui", "status", "exiting"))
            await client.shutdown()
        if not client.gui.close_requested:
            # user didn't request the closure
            client.gui.tray.change_icon("error")
            client.print(_("status", "terminated"))
            client.gui.status.update(_("gui", "status", "terminated"))
            # notify the user about the closure
            client.gui.grab_attention(sound=True)
        await client.gui.wait_until_closed()
        # save the application state
        # NOTE: we have to do it after wait_until_closed,
        # because the user can alter some settings between app termination and closing the window
        client.save(force=True)
        client.gui.stop()
        client.gui.close_window()
        sys.exit(exit_status)

    with lock.file:
        asyncio.run(main())
