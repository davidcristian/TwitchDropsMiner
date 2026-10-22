# The AppImage job installs the newest release of appimage-builder's dependencies

**Status:** done 2026-10-22
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
- 2026-10-22: `constraints.txt` sets the 12 packages that release 1.1.0 requires and those they depend on, 22 in
  all, of which 19 are new lines. Each new line is the newest release that was two weeks old, the same for
  `x86_64` and `aarch64` ([runbooks/dependency-versions.md](../../runbooks/dependency-versions.md)), and
  `tests/test_constraints.py` checks that the 12 have lines. Still open: reading `setup.py` at the commit, which
  needs GitHub, and the log of a run of the AppImage job.
- 2026-10-22: Closed. `setup.py` at the commit requires libconf and pydpkg besides the 12 requirements of
  release 1.1.0, and sets no version range except `pyyaml>=5`. `constraints.txt` sets them and the 7 packages
  they depend on. Each new line is the newest release that was two weeks old, except that pydpkg 1.9.5
  requires PGPy13 0.6.1rc1, a pre-release, and a zstandard below 0.24, so the file sets zstandard 0.23.0. The
  runbook resolves a wheel built from the commit, and `tests/test_constraints.py` checks that the commit in
  `ci.yml` is the one whose requirements it lists. In fresh `ubuntu:22.04` containers for `amd64` and `arm64`,
  a user without root ran the job's four pip commands as `ci.yml` writes them. Each `pip freeze --all` listed
  appimage-builder from the commit and 38 packages at the version in the file, and nothing else. Ubuntu's own
  pip 22.0.2, setuptools 59.6.0 and wheel 0.37.1 stay in `/usr/lib/python3/dist-packages`, and the versions in
  the user site replace them. The GitHub runner image has more system packages, but pip keeps one that the job
  needs only at the version in the file and installs that version over any other, so the job installs the same
  versions.
