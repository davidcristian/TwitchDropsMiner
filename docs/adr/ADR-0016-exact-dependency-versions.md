# ADR-0016: Exact versions of the packages the builds install

**Status:** Accepted (2026-10-22)

## Context

`requirements.txt` sets a range for aiohttp, an upper limit for PyGObject and no version for Pillow, pystray,
pywin32 or truststore. The build jobs in `.github/workflows/ci.yml`, `build.sh` and `build.bat` installed
PyInstaller with no version, and the AppImage job and recipe installed pip, wheel, setuptools, setuptools_scm,
meson and ninja the same way. Each build therefore installed the newest release on PyPI that day, with the
packages that release depends on:

- a broken or malicious release of any of these packages went into the next build;
- no release could be built again as it was, and nothing recorded the versions once the CI logs expired.

On 2026-10-21 a new environment got Pillow 13.0.0, released on 2026-10-16, while the log of the last release
build named Pillow 12.3.0. Pillow 13 requires Python 3.11, and the AppImage and three of the four Validate runs
use 3.10. [Task 048](../refinements/tasks/048-builds-install-the-newest-dependencies.md) recorded the gap.

## Decision

1. **`constraints.txt` sets the exact version of every package that a build installs from PyPI**: the packages
   of `requirements.txt` and PyInstaller with the packages they depend on, pip and wheel, the packages that pip
   needs to build PyGObject and pycairo from source on Linux (meson-python, meson, ninja, patchelf and theirs),
   the tools that the AppImage job installs before appimage-builder, and the packages that appimage-builder
   needs, as `setup.py` at the commit that the AppImage job installs names them. It covers every build:
   Python 3.14 on Windows `x86_64`, macOS `arm64` and Linux `x86_64` and `aarch64`, and Python 3.10 on Linux
   for the AppImage. A package that only some builds install has one line, which the others ignore.
   `requirements.txt` keeps its ranges for a person who installs it into an environment of their own.
2. **Every `pip install` of a build passes `-c constraints.txt`**, in the build jobs of `ci.yml`, the AppImage
   recipe, `setup_env.sh`, `setup_env.bat`, `build.sh` and `build.bat`. Each one that installs
   `requirements.txt`, PyInstaller or appimage-builder also passes `--build-constraint constraints.txt`. `-c`
   sets the versions that pip installs, but since pip 26.2 it does not apply to the separate environment in which
   pip builds a package from source; `--build-constraint`, which pip 25.3 added, does. So the build jobs, the
   recipe and the setup scripts first install the pip version in the file, and `build.sh` and `build.bat` use
   the pip that `setup_env` installed.
3. **The Validate job installs `requirements-dev.txt` with `-c constraints.txt`.** The tests then run on the
   versions that the releases contain, and a new release of a package can fail only the pull request that
   moves the file to it. The check tools keep their exact versions in `requirements-dev.txt`
   ([ADR-0012](ADR-0012-check-command.md)), and the file does not set the packages they depend on. The job
   passes no `--build-constraint`: the pip that Python 3.10 includes, 23.0.1, does not have the option.
   `requirements-dev.txt` also names the file in a `-c constraints.txt` line, the only way in which GitHub's
   dependency graph reads it.
4. **No hashes.** pip runs without `--require-hashes`, for the reasons under Alternatives rejected.
5. **Dependabot proposes the new versions,** in one pull request a month and at once for a release that fixes
   a security issue, and each pull request runs every build. A new version is the newest release that has been
   on PyPI for at least two weeks, as for the check tools, except a security release. The `pip` entry in
   `.github/dependabot.yml` sets this with `cooldown`, which security updates skip, and its settings are
   explained in [building.md](../building.md#exact-versions). A pull request that changes `requirements.txt`,
   the app's lines of `requirements-dev.txt`, `BUILD_PYTHON_VERSION` or the Ubuntu release of the Linux builds
   updates the file too. [runbooks/dependency-versions.md](../runbooks/dependency-versions.md) gives the
   commands, and checks a pull request of Dependabot.
6. **Each build job checks what pip installed.** After the installs, `scripts/installcheck.py` fails on a
   package that the file lacks or sets to another version. The PyInstaller jobs check every package that their
   Python can import. The AppImage job checks the user's site folder, into which pip installs as a user without
   root, and so leaves out the Debian packages of Ubuntu's Python; after the build it checks the app's packages
   in the AppDir.

## Consequences

- A build installs the same versions until a pull request changes `constraints.txt`, and git records which
  versions each commit was built with.
- `tests/test_constraints.py` checks that every `pip install` in `ci.yml`, the recipe and the scripts passes
  `-c constraints.txt`, that every package they or `requirements.txt` name has a line in the file, and that every
  line sets one exact version.
- The first file keeps Pillow 12.3.0, aiohttp 3.14.5 and PyInstaller 6.22.3, the versions that the log of the
  last release build names. Every other package has the newest release uploaded before 2026-10-07, at least two
  weeks before the file was written.
- PyPI never accepts a second file under a file name it already has, but a project can add a new file to an
  existing release, such as a wheel for another platform. pip can install such a file under a listed version.
- `setup_env` installs the same versions for a run from source. On 2026-10-21 every listed version also had a
  wheel for Python 3.11, 3.12 and 3.13 on Windows, macOS `arm64` and Linux `x86_64`. On a Python that a listed
  version has no wheel for, pip builds that package from source, which can fail; `pip install -r
  requirements.txt` without the file then installs the newest versions.
- A package that drops Python 3.10, as Pillow 13 does, needs two lines with `python_version` markers before the
  3.14 builds can move to its new version.
- The AppImage job installs appimage-builder from a git commit, and its lines in the file follow the
  `install_requires` of `setup.py` at that commit: the 12 requirements of release 1.1.0 on PyPI, and libconf and
  pydpkg. pydpkg 1.9.5 requires PGPy13 0.6.1rc1, a pre-release, and a zstandard below 0.24, so the file sets
  zstandard 0.23.0 rather than its newest release. A resolve for another platform accepts only wheels, so the
  runbook builds a wheel of the commit first. `tests/test_constraints.py` checks that the commit in `ci.yml` is
  the one whose requirements it lists.
- Dependabot's `pip` updates read every `.txt` file in the root whose name contains `requirements` or whose
  lines are all requirements, options or comments, so they read and update `constraints.txt` as it is. They move
  each line to its newest version on its own, without resolving the whole set. A limit that another package sets
  therefore goes into `ignore`, and a new dependency of a new version fails the check of the build jobs until the
  runbook adds its line.
- Dependabot reads the Python versions that a release supports for Python 3.14, so its pull request for a
  release that drops Python 3.10 fails the jobs on 3.10 until two lines with markers replace the one. It leaves
  out a line whose `python_version` marker does not hold on 3.14.
- A commit message of Dependabot has a subject that follows the commit rules and a body that does not, so the
  pull request is merged with a squash and a rewritten message.
- A security update needs Dependabot alerts and security updates turned on in the repository settings. The
  alerts come from the dependency graph. It reads a `.txt` file whose name does not contain a word such as
  `requirements` only when a file whose name does names it with `-r` or `-c`, as `requirements-dev.txt` does.
- On 2026-10-21, with pip 26.2.1:
  - the runbook's resolve for the eight pairs of platform and Python, with each target's markers, chose every
    package at the version in the file;
  - on a CPython 3.14.7, `setup_env.sh` built PyGObject 3.50.2 and pycairo 1.29.2 with the build packages of the
    file, `just check` passed with `requirements-dev.txt` installed with the file, and `build.sh` built an
    executable. Without the tray library, which that machine lacks, it showed its window on Xvfb and retried its
    connection with the network blocked;
  - on a CPython 3.10.20, the pip lines of the AppImage recipe and job installed the versions in the file;
  - with a copy of the file that set meson 1.12.0, `-c` alone gave the build environment of PyGObject meson
    1.12.1, the newest, and `--build-constraint` gave it 1.12.0.
- On 2026-10-22, in fresh `ubuntu:22.04` containers for `amd64` and `arm64`, a user without root ran the four
  pip commands of the AppImage job, with Ubuntu's Python 3.10.12 and pip 22.0.2, as the job does on GitHub. pip
  installed appimage-builder from the commit and 38 packages, each at the version in the file. It built
  appimage-builder and jsonpath-rw from source, in build environments whose 6 packages were also at those
  versions. The runbook's resolve chose the same versions for `x86_64` and `aarch64`.
- On 2026-10-22, the commands of the new check steps passed after the job's installs: with setup-python's
  CPython 3.14.9 in the act image for `ubuntu-22.04`, on 23 packages, and as a user without root in a fresh
  `ubuntu:22.04` container, on 39 packages in the user's site folder and 18 in the AppDir. Each failed with six
  1.16.0 or idna 3.10 in place of the version in the file, and with colorama, which the file lacks. Run without
  `--folder` in the AppImage container, the check reported 13 Debian packages.
- Not checked: the installs on Windows and macOS, the pip 22.0.2 of Ubuntu 22.04 in the AppImage recipe, which
  replaces it first, and a run of Dependabot and the dependency graph, which happen only on GitHub. The CI run of
  the pull request shows the first two, and the first pull request of Dependabot and the dependency graph page
  of the repository show the others.

## Alternatives rejected

- **Hashes with `--require-hashes`.** pip would then refuse a file whose hash the list lacks. But the builds
  install 89 wheels and 2 source archives across the eight pairs, each update changes the hashes of every
  platform, and two installs stay unchecked: in hash mode pip installs the packages of a build from source
  without hashes, and it refuses a requirement from a git commit, which is how the AppImage job installs
  appimage-builder. Both were checked with pip 26.2.1.
- **Exact versions in `requirements.txt`.** It lists only the direct dependencies, and a person who installs it
  into an environment of their own could no longer take another version.
- **A lock file from `pip-compile` or `uv pip compile`.** Each is a new dependency of the repo, and pip alone
  resolves each platform, as the runbook does.

## Related

- [building.md](../building.md#exact-versions): what the builds install and how.
- [runbooks/dependency-versions.md](../runbooks/dependency-versions.md): updating a version.
- [ADR-0012](ADR-0012-check-command.md): the Validate job and the versions of the check tools.
- [ADR-0015](ADR-0015-release-build-python.md): the Python of the builds.
- Tasks [048](../refinements/tasks/048-builds-install-the-newest-dependencies.md) and
  [057](../refinements/tasks/057-constraints-updates-by-hand.md) (closed by this record), and
  [056](../refinements/tasks/056-appimage-builder-dependencies-newest.md).
