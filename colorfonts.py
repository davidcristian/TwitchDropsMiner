"""Leaves color fonts out of the fonts that Tk draws with when its libXft is too old to draw them."""
from __future__ import annotations

import ctypes
import logging
from collections import abc
from typing import Protocol


logger = logging.getLogger("TwitchDrops")

# What XftGetVersion returns for libXft 2.3.5, the first release that draws the color glyphs of emoji fonts
COLOR_XFT_VERSION = 20305
NO_COLOR_FONTS = (
    b"<fontconfig><selectfont><rejectfont><pattern>"
    b'<patelt name="color"><bool>true</bool></patelt>'
    b"</pattern></rejectfont></selectfont></fontconfig>"
)


class FontLibraries(Protocol):
    def xft_version(self) -> int | None:
        """Return the version of libXft, such as 20304 for 2.3.4, or None when it does not load."""

    def use_fontconfig_rules(self, rules: bytes) -> bool:
        """Make the user's fontconfig files plus rules the configuration Tk uses, and return whether it did."""


class LoadedFontLibraries:
    """The calls of `FontLibraries` to the libXft and libfontconfig that Tk loads, through `ctypes`.

    load opens a library by its name, as `ctypes.CDLL` does."""

    def __init__(self, load: abc.Callable[[str], ctypes.CDLL] = ctypes.CDLL) -> None:
        self._load = load

    def xft_version(self) -> int | None:
        try:
            return int(self._load("libXft.so.2").XftGetVersion())
        except OSError:
            return None

    def use_fontconfig_rules(self, rules: bytes) -> bool:
        try:
            fontconfig = self._load("libfontconfig.so.1")
            fontconfig.FcInitLoadConfig.restype = ctypes.c_void_p
            fontconfig.FcConfigParseAndLoadFromMemory.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            for name in ("FcConfigBuildFonts", "FcConfigSetCurrent", "FcConfigDestroy"):
                getattr(fontconfig, name).argtypes = [ctypes.c_void_p]
        except (OSError, AttributeError):
            return False
        config = fontconfig.FcInitLoadConfig()
        if not config:
            return False
        # the configuration stays in use until the app ends, so it is destroyed only when it did not become current
        if (
            fontconfig.FcConfigParseAndLoadFromMemory(config, rules, True)
            and fontconfig.FcConfigBuildFonts(config)
            and fontconfig.FcConfigSetCurrent(config)
        ):
            return True
        fontconfig.FcConfigDestroy(config)
        return False


def skip_color_fonts(libraries: FontLibraries) -> bool:
    """Make fontconfig leave out color fonts when libXft is older than 2.3.5, and return whether it did."""
    version = libraries.xft_version()
    if version is None or version >= COLOR_XFT_VERSION:
        return False
    if not libraries.use_fontconfig_rules(NO_COLOR_FONTS):
        return False
    major, minor, revision = version // 10000, version // 100 % 100, version % 100
    logger.info(f"libXft {major}.{minor}.{revision} cannot draw color fonts, so Tk does not use them")
    return True
