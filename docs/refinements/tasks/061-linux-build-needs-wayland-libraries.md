# The Linux builds stop at start without the Wayland client libraries

**Status:** open
**Area:** build, appimage, gui
**Origin:** Found on 2026-10-22 while the build of the `linux-pyinstaller` job was started in an Ubuntu 22.04
container that had only an X server, fonts and `unzip` installed
**Verified:** 2026-10-22

PyInstaller leaves out of every Linux build the libraries that it expects from the system's graphics stack: its
`_unix_excludes` list in `PyInstaller/depend/dylib.py` names `libwayland-client`, `libwayland-cursor`,
`libwayland-egl`, `libxcb`, `libdrm` and the GL libraries. The bundled `libgdk-3.so.0` needs the three Wayland
libraries. On a system without them, `import pystray` in `gui.py` loads pystray's AppIndicator backend, and
PyGObject's `Gdk` override fails with an `AssertionError` after this warning:

```text
Failed to load shared library 'libgdk-3.so.0' referenced by the typelib: libwayland-cursor.so.0: cannot open shared object file: No such file or directory
```

pystray moves on to its next backend only after an `ImportError`, so the app stops before its window opens. It
prints the traceback to standard error, and the screen shows nothing. The README's Linux notes name only glibc
2.35 and a display server as requirements.

On 2026-10-22, the x86_64 build from the job, made with PyInstaller 6.22.3, ran under Xvfb in an `ubuntu:22.04`
container with `xvfb`, `xauth`, `unzip`, `python3-pil` and two font packages. `ldd` over every library of the
extracted build reported only `libwayland-client.so.0`, `libwayland-cursor.so.0` and `libwayland-egl.so.1` as not
found, apart from `librsvg-2.so.2`, which `build.spec` leaves out. The app stopped as above. With
`libwayland-client0`, `libwayland-cursor0` and `libwayland-egl1` added, its window opened.

The AppImage has the same gap. appimage-builder leaves out of every AppImage the Ubuntu packages that the
`graphics` list in `appimagebuilder/modules/deploy/apt/listings.py` names, unless the recipe's `include` names
them: `libwayland-*`, `libxcb1`, `libxcb-render0`, `libx11-*` and the GL packages. Its bundled `libgdk-3.so.0`
needs `libxcb-render.so.0` and the three Wayland libraries. On 2026-10-22, the `x86_64` and `aarch64` AppImages
from the job ran with `APPIMAGE_EXTRACT_AND_RUN=1` under Xvfb in an `ubuntu:22.04` container with `xvfb`,
`xauth`, `fontconfig-config` and two font packages, `aarch64` under QEMU
([runbook](../../runbooks/linux-ci-with-act.md#start-an-appimage)). `ldd` over the extracted files reported
only these four libraries as not found, apart from `libsqlite3.so.0` and `libtiff.so.5`, which the recipe leaves
out. The app stopped as above. With the three Wayland packages added, it stopped on `libxcb-render.so.0`, and
with `libxcb-render0` too, its window opened.

On Debian and Ubuntu, `libgtk-3-0` depends on the three Wayland packages and, through `libcairo2`, on
`libxcb-render0`, so a desktop with GTK 3 has them, and the gap matters on a minimal X11 system.

## What a fix involves

One of:

- Name the libraries in the README's Linux notes and in [troubleshooting.md](../../troubleshooting.md), with
  the Debian and Ubuntu package names, and `libxcb-render0` for the AppImage.
- Catch the failure of the AppIndicator backend and start pystray's `xorg` backend, which needs only X11. The
  import is in `gui.py`, which is over the line cap
  ([task 005](005-modules-over-the-line-cap.md)), so the code goes in a new module. Whether the AppImage then
  starts without `libxcb-render0` was not checked.

Bundling the libraries, with `build.spec` or with the `include` list of the AppImage recipe, goes against the
reason both tools leave them out: a bundled Wayland library can differ from the one that the system's
compositor and drivers use, and appimage-builder's list names problems with the NVIDIA driver. None of this
sends a Twitch request.

## History

- 2026-10-22: Opened. Found while each build of the `linux-pyinstaller` job was started under Xvfb with no
  network.
- 2026-10-22: Each AppImage of the `linux-appimage` job, run under act, stops the same way without the three
  Wayland libraries or `libxcb-render0`, which appimage-builder leaves out. The title was "The Linux PyInstaller
  build stops at start without the Wayland client libraries".
