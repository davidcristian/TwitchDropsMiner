"""The window icon, the browser, and the paths of the files bundled with the app."""
from __future__ import annotations

import os
import sys
import webbrowser
import tkinter as tk
from pathlib import Path

from yarl import URL
from PIL.ImageTk import PhotoImage
from PIL import Image as Image_module

from constants import IS_PACKAGED
from constants import _resource_path as resource_path  # noqa


def set_root_icon(root: tk.Tk, image_path: Path | str) -> None:
    with Image_module.open(image_path) as image:
        icon_photo = PhotoImage(master=root, image=image)
    root.iconphoto(True, icon_photo)  # type: ignore[arg-type]
    # keep a reference to the PhotoImage to avoid the ResourceWarning
    root._icon_image = icon_photo  # type: ignore[attr-defined]


def webopen(url: URL | str):
    url_str = str(url)
    if IS_PACKAGED and sys.platform == "linux":
        # https://pyinstaller.org/en/stable/
        # runtime-information.html#ld-library-path-libpath-considerations
        # NOTE: All 4 cases need to be handled here: either of the two values can be there or not.
        ld_env = "LD_LIBRARY_PATH"
        ld_path_curr = os.environ.get(ld_env)
        ld_path_orig = os.environ.get(f"{ld_env}_ORIG")
        if ld_path_orig is not None:
            os.environ[ld_env] = ld_path_orig
        elif ld_path_curr is not None:
            # pop current
            os.environ.pop(ld_env)

        webbrowser.open_new_tab(url_str)

        if ld_path_curr is not None:
            os.environ[ld_env] = ld_path_curr
        elif ld_path_orig is not None:
            # pop original
            os.environ.pop(ld_env)
    else:
        webbrowser.open_new_tab(url_str)
