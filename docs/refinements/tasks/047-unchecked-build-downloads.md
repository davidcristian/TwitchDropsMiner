# The hash checks of the Linux build downloads have not run in CI

**Status:** open
**Area:** ci, appimage
**Origin:** Found on 2026-10-21 while the apt key URL in `appimage/AppImageBuilder.yml` moved to HTTPS: the
recipe printed the SHA-256 of the libXft archive and compared it with nothing
**Verified:** 2026-10-21

The Linux builds check three downloads against a SHA-256 written in the repo
([building.md](../../building.md#build-the-appimage)):

- **libXft 2.3.9.** The `linux-pyinstaller` job in `.github/workflows/ci.yml` and the `script` of
  `appimage/AppImageBuilder.yml` check the archive with `sha256sum -c` before they build it.
- **The AppImage runtime and AppRun.** The recipe downloads the runtime of the type2-runtime release `20251108`
  and AppRun v2.0.0 with its hooks library, checks them against `appimage/runtime-<arch>.sha256`, and puts them
  in appimage-builder's build folder. After the build, a step of the `linux-appimage` job compares the start of
  the AppImage, its `AppRun` and its `libapprun_hooks.so` with those files.

None of these steps has run in CI. How appimage-builder takes the files was read in its source at the commit the
job installs, not run: `AppImagePrimer` downloads the runtime only when `prime/runtime-<arch>` is missing from
its build folder, and `AppRunBinariesResolver` downloads an AppRun file only when `AppRun/<version>/` lacks it.
Until this change the AppImage had the `continuous` runtime, which is newer than `20251108`.

## What a fix involves

A pull request run, and a start of each AppImage it builds, show:

1. that the `sha256sum -c` lines pass in both `linux-pyinstaller` jobs and both `linux-appimage` jobs;
2. that the appimage-builder log has no `Downloading:` line for the runtime or for AppRun, and that the step that
   compares the AppImage with the checked files passes for `x86_64` and `aarch64`;
3. that the `x86_64` and `aarch64` AppImages start and show the window, as they did with the `continuous`
   runtime.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the apt key URL of the AppImage recipe moved from HTTP to HTTPS.
- 2026-10-21: The builds check libXft, the runtime and AppRun against a SHA-256, compared with the libXft and
  runtime signatures and with Homebrew's libXft formula ([building.md](../../building.md#build-the-appimage)).
  The recipe downloaded and checked all three for both architectures, and a hand-made AppImage with the `x86_64`
  runtime started through FUSE and through `APPIMAGE_EXTRACT_AND_RUN`. The title was "The libXft archive and the
  AppImage runtime are not checked against a known hash". The task stays open until a CI run and a start of
  each AppImage show the steps above.
