# `colorfonts.py`

**Purpose.** On X11, Tk draws text with libXft, which finds fonts through fontconfig. libXft before 2.3.5, such
as 2.3.4 on Ubuntu 22.04, cannot draw the color glyphs of emoji fonts such as Noto Color Emoji. When Tk measures
or draws a symbol that it takes from such a font, libXft sends the glyph, 136 by 128 pixels, in a form the X
server rejects with a `BadLength` error for `RenderAddGlyphs`. Tk 8.6.12 catches the error, but the `XSync`
with which its `Tk_DeleteErrorHandler` collects errors sometimes ends the app with a segmentation fault inside
libX11 1.7.5. The window's own text has such symbols: ❌, ⏳, ➕, 🎁, 📋 and 🌐. A system is affected when the
first font in fontconfig's order that has such a symbol is a color font, as with only DejaVu and Noto Color Emoji
installed ([task 067](../refinements/tasks/067-gui-preview-crashes-under-openbox.md) has the counts).

`skip_color_fonts` makes fontconfig leave out every color font when the loaded libXft is older than 2.3.5, so
Tk takes each symbol from a font without color, or draws an empty box when no font has it. libXft 2.3.4 draws
nothing for a glyph of a color font, so the window loses no symbol that it showed. Removing the symbols from the
window's text would change it on every platform, and text from Twitch, such as a campaign name, can contain
emoji too. With libXft 2.3.5 or newer, and on Windows and macOS, where no libXft loads, nothing changes. The
release builds for Linux include libXft 2.3.9 ([building.md](../building.md#build-the-appimage)), so only a run
from source changes.

## Public contract

- `skip_color_fonts(libraries)` returns whether it made fontconfig leave out color fonts. `GUIManager.__init__`
  in `gui.py` and `ask_on_top` in `folderpicker.py` call it with `LoadedFontLibraries()` before they create
  their `Tk` root.
  - It returns False and changes nothing when `libraries.xft_version()` returns None or at least
    `COLOR_XFT_VERSION` (20305, which is 2.3.5).
  - Otherwise it passes `NO_COLOR_FONTS`, a fontconfig `rejectfont` rule for the `color` property, to
    `libraries.use_fontconfig_rules`. When that returns True, it logs `libXft <version> cannot draw color fonts`
    at INFO and returns True; otherwise it returns False.
- `FontLibraries` is the `Protocol` of the two calls it makes. Tests pass a fake one.
- `LoadedFontLibraries` makes them through `ctypes`:
  - `xft_version()` returns `XftGetVersion()` of `libXft.so.2`, or None when the library does not load.
  - `use_fontconfig_rules(rules)` loads `libfontconfig.so.1` and creates a configuration from the user's
    fontconfig files with `FcInitLoadConfig`. It adds `rules` with `FcConfigParseAndLoadFromMemory`, loads the
    fonts with `FcConfigBuildFonts` and makes the result current with `FcConfigSetCurrent`, which Tk's
    `FcFontSort` calls then read. It returns False when the library or one of these functions is missing, and
    returns False and destroys the configuration when a step fails.

## Invariants

- The dynamic loader returns a library that the process has already loaded under the same name, so
  `ctypes.CDLL("libXft.so.2")` returns the libXft that Tk uses, also the one that a PyInstaller build includes.
- `main.py` creates a hidden `Tk` root for its argument errors before the window. Its fonts keep the earlier
  configuration, and it shows no emoji. Each `Tk` root sorts its fonts when it creates them, so the window's
  root reads the new configuration.
- The current configuration stays in use until the app ends, so it is never destroyed.

`tests/test_colorfonts.py` checks each case with fakes, of the two libraries too, and in a child process checks
that the real rule leaves the color fonts out of the list of fonts that fontconfig returns. `tests/test_gui.py` checks that the window
applies the rule before it creates its `Tk` root.

**Dependencies.** None: the standard library only.
