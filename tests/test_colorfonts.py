from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from colorfonts import COLOR_XFT_VERSION, NO_COLOR_FONTS, LoadedFontLibraries, skip_color_fonts

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("FcConfigParseAndLoadFromMemory", "FcConfigBuildFonts", "FcConfigSetCurrent")
CONFIG = 7

# Prints the number of color fonts that fontconfig lists before and after the rules, and whether they applied.
COUNT_COLOR_FONTS = """
import ctypes
from colorfonts import NO_COLOR_FONTS, LoadedFontLibraries

fc = ctypes.CDLL("libfontconfig.so.1")
fc.FcPatternCreate.restype = fc.FcObjectSetCreate.restype = fc.FcFontList.restype = ctypes.c_void_p
fc.FcPatternAddBool.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
fc.FcObjectSetAdd.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
fc.FcFontList.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
fc.FcFontSetDestroy.argtypes = [ctypes.c_void_p]

def color_fonts():
    pattern, objects = fc.FcPatternCreate(), fc.FcObjectSetCreate()
    fc.FcPatternAddBool(pattern, b"color", 1)
    fc.FcObjectSetAdd(objects, b"file")
    fonts = fc.FcFontList(None, pattern, objects)
    count = ctypes.cast(fonts, ctypes.POINTER(ctypes.c_int))[0]
    fc.FcFontSetDestroy(fonts)
    return count

before = color_fonts()
applied = LoadedFontLibraries().use_fontconfig_rules(NO_COLOR_FONTS)
print(before, applied, color_fonts())
"""


class FakeLibraries:
    def __init__(self, version: int | None, applies: bool = True) -> None:
        self.version = version
        self.applies = applies
        self.rules: list[bytes] = []

    def xft_version(self) -> int | None:
        return self.version

    def use_fontconfig_rules(self, rules: bytes) -> bool:
        self.rules.append(rules)
        return self.applies


class FakeXft:
    def XftGetVersion(self) -> int:
        return 20304


class FakeFontconfig:
    """Functions with the names of libfontconfig's, which record their calls; fails names the one that fails."""

    def __init__(self, config: int | None = CONFIG, fails: str = "", missing: str = "") -> None:
        self.calls: list[tuple[object, ...]] = []
        names = ["FcInitLoadConfig", *STEPS, "FcConfigDestroy"]
        for name in names:
            if name != missing:
                result = config if name == "FcInitLoadConfig" else int(name != fails)
                setattr(self, name, self._function(name, result))

    def _function(self, name: str, result: object):
        def function(*args):
            self.calls.append((name, *args))
            return result

        return function


def loader(**libraries: object):
    def load(name: str):
        if name not in libraries:
            raise OSError(f"{name}: cannot open shared object file: No such file or directory")
        return libraries[name]

    return load


def loads(name: str) -> bool:
    try:
        ctypes.CDLL(name)
    except OSError:
        return False
    return True


def test_libxft_2_3_4_gets_the_rules_that_leave_color_fonts_out(caplog):
    libraries = FakeLibraries(20304)
    with caplog.at_level(logging.INFO, logger="TwitchDrops"):
        assert skip_color_fonts(libraries) is True
    assert libraries.rules == [NO_COLOR_FONTS]
    assert "libXft 2.3.4 cannot draw color fonts" in caplog.text


@pytest.mark.parametrize("version", [COLOR_XFT_VERSION, 20306, 20309, 30000])
def test_libxft_2_3_5_and_newer_keep_color_fonts(version):
    libraries = FakeLibraries(version)
    assert skip_color_fonts(libraries) is False
    assert libraries.rules == []


def test_no_libxft_keeps_color_fonts():
    libraries = FakeLibraries(None)
    assert skip_color_fonts(libraries) is False
    assert libraries.rules == []


def test_rules_that_fontconfig_does_not_take_report_no_change(caplog):
    libraries = FakeLibraries(20304, applies=False)
    with caplog.at_level(logging.INFO, logger="TwitchDrops"):
        assert skip_color_fonts(libraries) is False
    assert libraries.rules == [NO_COLOR_FONTS]
    assert caplog.text == ""


def test_the_xft_version_is_what_xftgetversion_of_libxft_returns():
    assert LoadedFontLibraries(loader(**{"libXft.so.2": FakeXft()})).xft_version() == 20304


def test_a_libxft_that_does_not_load_has_no_version():
    assert LoadedFontLibraries(loader()).xft_version() is None


def test_the_rules_become_the_current_configuration_of_the_user_files():
    fontconfig = FakeFontconfig()
    libraries = LoadedFontLibraries(loader(**{"libfontconfig.so.1": fontconfig}))
    assert libraries.use_fontconfig_rules(NO_COLOR_FONTS) is True
    assert fontconfig.calls == [
        ("FcInitLoadConfig",),
        ("FcConfigParseAndLoadFromMemory", CONFIG, NO_COLOR_FONTS, True),
        ("FcConfigBuildFonts", CONFIG),
        ("FcConfigSetCurrent", CONFIG),
    ]


@pytest.mark.parametrize("step", STEPS)
def test_a_failed_step_destroys_the_configuration_and_makes_nothing_current(step):
    fontconfig = FakeFontconfig(fails=step)
    libraries = LoadedFontLibraries(loader(**{"libfontconfig.so.1": fontconfig}))
    assert libraries.use_fontconfig_rules(NO_COLOR_FONTS) is False
    names = [call[0] for call in fontconfig.calls]
    assert names == ["FcInitLoadConfig", *STEPS[: STEPS.index(step) + 1], "FcConfigDestroy"]
    assert fontconfig.calls[-1] == ("FcConfigDestroy", CONFIG)


def test_no_configuration_from_fontconfig_takes_no_rules():
    fontconfig = FakeFontconfig(config=None)
    libraries = LoadedFontLibraries(loader(**{"libfontconfig.so.1": fontconfig}))
    assert libraries.use_fontconfig_rules(NO_COLOR_FONTS) is False
    assert fontconfig.calls == [("FcInitLoadConfig",)]


def test_a_libfontconfig_without_rules_from_memory_is_not_called():
    fontconfig = FakeFontconfig(missing="FcConfigParseAndLoadFromMemory")
    libraries = LoadedFontLibraries(loader(**{"libfontconfig.so.1": fontconfig}))
    assert libraries.use_fontconfig_rules(NO_COLOR_FONTS) is False
    assert fontconfig.calls == []


def test_a_libfontconfig_that_does_not_load_takes_no_rules():
    assert LoadedFontLibraries(loader()).use_fontconfig_rules(NO_COLOR_FONTS) is False


@pytest.mark.skipif(not loads("libXft.so.2"), reason="needs libXft")
def test_the_loaded_libxft_has_a_version_of_2_x():
    version = LoadedFontLibraries().xft_version()
    assert version is not None and 20000 <= version < 30000


@pytest.mark.skipif(not loads("libfontconfig.so.1"), reason="needs libfontconfig")
def test_the_rules_leave_every_color_font_out_of_the_fonts_that_fontconfig_lists():
    # a child process, so that the configuration of the fonts that this process draws with stays as it is
    result = subprocess.run(
        [sys.executable, "-c", COUNT_COLOR_FONTS], cwd=ROOT, capture_output=True, text=True, check=True
    )
    before, applied, after = result.stdout.split()
    if before == "0":
        pytest.skip("needs a color font, such as Noto Color Emoji")
    assert (applied, after) == ("True", "0")
