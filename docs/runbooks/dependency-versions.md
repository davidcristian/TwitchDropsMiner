# Runbook: updating the versions in constraints.txt

`constraints.txt` sets the exact version of every package that a build installs from PyPI
([ADR-0016](../adr/ADR-0016-exact-dependency-versions.md)). This runbook finds new versions, resolves them for
every build and checks that the file lists every package that each build installs. Its commands read PyPI and
send no Twitch request. Run every command from the repository folder, on Linux, with a `python3.14` command.

## When

- Once a month, and at once when a release fixes a security issue in a listed package.
- In the pull request that changes `requirements.txt`, the app's lines in `requirements-dev.txt`,
  `BUILD_PYTHON_VERSION` in `ci.yml` or the Ubuntu release of the Linux builds.

A new version is the newest release that has been on PyPI for at least two weeks, as for the tools in
`requirements-dev.txt` ([ADR-0012](../adr/ADR-0012-check-command.md)). A release that fixes a security issue
needs no wait.

## Set up the resolver

pip chooses the wheels for the OS and Python that `--platform` and `--python-version` name, but it evaluates
the markers of a requirement, such as `sys_platform == "win32"`, for the Python that runs it. `target_pip.py`
sets those values for the target before pip starts, so that its report lists the packages the target installs.
`compare.py` prints each package of the reports whose version is not the one in `constraints.txt`, and each
line of the file that no report uses. Set `TDM` to a folder outside the repository:

```bash
export TDM=/tmp/tdm-resolve
python3.14 -m venv "$TDM/venv"
"$TDM/venv/bin/python" -m pip install -c constraints.txt pip
cat > "$TDM/target_pip.py" <<'EOF'
"""Run a pip dry run for another OS and Python: target_pip.py <platform> <python> <report> <pip arguments>."""
import sys

from pip._vendor.packaging import markers

tag, python, report = sys.argv[1:4]
arch = tag.split("_", 3)[-1] if tag.startswith("manylinux") else tag.rsplit("_", 1)[-1]
systems = {"win": ("win32", "Windows", "nt"), "mac": ("darwin", "Darwin", "posix"),
           "man": ("linux", "Linux", "posix")}
sys_platform, platform_system, os_name = systems[tag[:3]]
markers.default_environment = lambda: {
    "implementation_name": "cpython", "implementation_version": f"{python}.0", "os_name": os_name,
    "platform_machine": {"amd64": "AMD64"}.get(arch, arch), "platform_python_implementation": "CPython",
    "platform_release": "", "platform_system": platform_system, "platform_version": "",
    "python_full_version": f"{python}.0", "python_version": python, "sys_platform": sys_platform,
}
platforms = [tag]
if tag.startswith("manylinux"):
    platforms = [f"manylinux_2_{n}_{arch}" for n in range(17, 36)] + [f"manylinux2014_{arch}"]

from pip._internal.cli.main import main

options = ["--dry-run", "--ignore-installed", "--quiet", "--disable-pip-version-check", "--only-binary=:all:"]
options += ["--python-version", python, "--report", report] + [f"--platform={p}" for p in platforms]
sys.exit(main(["install", *options, *sys.argv[4:]]))
EOF
cat > "$TDM/compare.py" <<'EOF'
"""Print the packages of the reports in a folder that constraints.txt lacks or sets to another version."""
import json
import re
import sys
from pathlib import Path


def key(name):
    return re.sub(r"[-_.]+", "-", name).lower()


listed = {}
for line in Path("constraints.txt").read_text().splitlines():
    if line and not line.startswith("#"):
        name, version = line.split(";")[0].strip().split("==")
        listed.setdefault(key(name), set()).add(version)
found = {"pygobject", "pycairo"}
for report in sorted(Path(sys.argv[1]).glob("report-*.json")):
    for item in json.loads(report.read_text())["install"]:
        name, version = item["metadata"]["name"], item["metadata"]["version"]
        found.add(key(name))
        if version not in listed.get(key(name), ()):
            print(f"{report.stem}: {name}=={version}, constraints.txt: {sorted(listed.get(key(name), ()))}")
for name in sorted(set(listed) - found):
    print(f"no report installs {name}")
EOF
```

## Resolve for every build

The PyInstaller builds run Python 3.14 on four platforms, and the AppImage and the Validate job run Python
3.10, so `resolve` runs the eight pairs. PyGObject has no wheel for Linux, so `resolve` leaves it out, and it
asks for the packages of a build from source on Linux only, where the builds compile PyGObject and pycairo.
Define it in the same shell:

```bash
resolve() {
  rm -f "$TDM"/report-*.json
  grep -v PyGObject requirements.txt > "$TDM/requirements.txt"
  for python in 3.10 3.14; do
    for tag in win_amd64 macosx_11_0_arm64 manylinux_2_35_x86_64 manylinux_2_35_aarch64; do
      linux=""
      case $tag in manylinux*) linux="meson-python ninja patchelf" ;; esac
      "$TDM/venv/bin/python" "$TDM/target_pip.py" "$tag" "$python" "$TDM/report-$tag-$python.json" \
        -r "$TDM/requirements.txt" pip wheel pyinstaller setuptools setuptools_scm $linux "$@" \
        || echo "no resolution for $tag with Python $python"
    done
  done
}
```

1. List the newest versions that are two weeks old. Write into `$TDM/keep.txt` the lines of `constraints.txt`
   that must not change, or leave it empty:

   ```bash
   touch "$TDM/keep.txt"
   resolve --uploaded-prior-to P14D -c "$TDM/keep.txt"
   python3.14 "$TDM/compare.py" "$TDM"
   ```

   Each line that `compare.py` prints is a newer version, a new package or a package to remove.
2. Write the changes into `constraints.txt`, one `name==version` line per package, in the order of the names.
   A security release that is not two weeks old goes in by hand. When a package has dropped Python 3.10, the
   3.10 reports show an older version than the 3.14 ones: write both lines, each with a marker, such as
   `Pillow==12.3.0; python_version < "3.11"` and `Pillow==13.0.0; python_version >= "3.11"`.
3. Check the file. `resolve` must print no pip error and no `no resolution` line, and `compare.py` must print
   nothing:

   ```bash
   resolve -c constraints.txt
   python3.14 "$TDM/compare.py" "$TDM"
   ```

PyGObject and pycairo are built from source, so no report lists them. Choose their versions on their PyPI
pages, PyGObject below the limit in `requirements.txt`. `./setup_env.sh` builds both on Linux with the
packages in [building.md](../building.md#requirements), and so do the Linux builds in CI.

## Open the pull request

Commit `constraints.txt` with the change that needed it, or alone for an update, with a subject such as
`build: update aiohttp to 3.14.6`. The pull request runs the Validate job and every build with the new versions
([building.md](../building.md#release-builds)).

The file does not set the dependencies of appimage-builder, which the AppImage job installs from a git commit
([task 056](../refinements/tasks/056-appimage-builder-dependencies-newest.md)).
