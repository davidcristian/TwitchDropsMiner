# The libXft archive and the AppImage runtime are not checked against a known hash

**Status:** open
**Area:** ci, appimage
**Origin:** Found on 2026-10-21 while the apt key URL in `appimage/AppImageBuilder.yml` moved to HTTPS: the
recipe prints the SHA-256 of the libXft archive and compares it with nothing
**Verified:** 2026-10-21

Three downloads end up in the Linux releases, and none is compared with a known hash:

- **libXft 2.3.9.** The `linux-pyinstaller` job in `.github/workflows/ci.yml` and the `script` of
  `appimage/AppImageBuilder.yml` download `libXft-2.3.9.tar.xz` from `xorg.freedesktop.org` with `curl -fL`, run
  `sha256sum libXft.tar.xz`, and build what they downloaded. The hash only goes into the log, so a changed
  archive is built into both Linux releases.
- **The AppImage runtime and AppRun.** The recipe sets no runtime file and no hash, so appimage-builder
  downloads them itself. The last AppImage build log before 2026-10-21 names the `continuous` type 2 runtime
  and AppRun v2.0.0; check this again in the next log. The runtime is the first code that runs when a user
  starts the AppImage, and a `continuous` release can change between two builds.

No hash was added here, because each one needs the network to read from a source other than the download
itself.

## What a fix involves

1. **libXft.** Take the SHA-256 of `libXft-2.3.9.tar.xz` from the X.org release announcement on the
   xorg-announce mailing list, or check the archive's `.sig` file against the signer's key. Compare it with the
   hash in the last CI log. Replace each `sha256sum libXft.tar.xz` line with
   `echo "<hash>  libXft.tar.xz" | sha256sum -c`, in `ci.yml` and in the recipe, so that a different archive
   fails the build.
2. **The runtime.** Read the appimage-builder source at the commit the job installs and find whether the recipe
   can name a runtime file or a fixed runtime release. If it can, download a fixed release of the type 2 runtime
   for `x86_64` and `aarch64` in a job step, compare each with a hash written in `ci.yml`, and pass it to the
   recipe. If it cannot, record that in this file and in [building.md](../../building.md#build-the-appimage).
   Do the same for AppRun, and check whether the recipe's `AppDir.runtime` section can set its version.
3. Run the workflow on a pull request and start each AppImage once.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the apt key URL of the AppImage recipe moved from HTTP to HTTPS.
