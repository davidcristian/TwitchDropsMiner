# The AppImage job installs the newest release of appimage-builder's dependencies

**Status:** open
**Area:** ci, appimage
**Origin:** Found on 2026-10-21 while `constraints.txt` was written: the `setup.py` of appimage-builder at the
commit that the AppImage job installs differs from the one in its last release on PyPI
**Verified:** 2026-10-22

The `linux-appimage` job in `.github/workflows/ci.yml` installs appimage-builder from a fixed commit of its
GitHub repository, with `-c constraints.txt --build-constraint constraints.txt`
([ADR-0016](../../adr/ADR-0016-exact-dependency-versions.md)). The file sets pip, wheel, setuptools and
setuptools_scm with the packages they depend on, but not the packages that appimage-builder requires, so the job
installs their newest releases. These packages run during the build and write the AppImage, though none of them
ends up inside it.

Their list at that commit was not read. PyPI has appimage-builder up to release 1.1.0, from 2022, and the git
blob hash of its `setup.py` differs from that of the `setup.py` at the commit. Release 1.1.0 requires PyYAML,
docker, requests, schema, packaging, questionary, emrichen, ruamel.yaml, roam, urllib3, lief and python-gnupg.
On 2026-10-21, pip 26.2.1 on Python 3.10 resolved them with the file to 21 packages besides those already
installed, among them lief 1.0.0 and requests 2.34.2. The file sets only idna and six of these.

## What a fix involves

Read `setup.py` at the commit that the job names, resolve its requirements on Python 3.10 for `x86_64` and
`aarch64` as [runbooks/dependency-versions.md](../../runbooks/dependency-versions.md) does, and add them to
`constraints.txt`. A run of the AppImage job then shows in its log that pip installed no other package. Reading
the commit needs the network for GitHub. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while `constraints.txt` was written, when the dependencies of appimage-builder at the
  commit that the job installs could not be read from PyPI.
