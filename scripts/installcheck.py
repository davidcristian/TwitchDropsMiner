"""Fail when pip installed a package that constraints.txt lacks or sets to another version."""
from __future__ import annotations

import argparse
import operator
import os
import platform
import re
import sys
from collections.abc import Iterable, Mapping
from importlib import metadata
from pathlib import Path
from typing import NamedTuple

from sources import ROOT


_LINE = re.compile(r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*(?P<version>[^\s;]+)\s*(?:;\s*(?P<marker>.+))?")
_CLAUSE = re.compile(r"""(?P<name>\w+)\s*(?P<op>==|!=|<=|>=|<|>)\s*(?P<quote>["'])(?P<value>[^"']*)(?P=quote)""")
_NUMBERS = re.compile(r"\d+(?:\.\d+)*")
_OPERATORS = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge
}
# The marker names whose values compare as versions. The others compare as text, with == and != only.
VERSION_NAMES = ("python_version", "python_full_version")


class Package(NamedTuple):
    """One installed distribution: its name and version as its metadata gives them, and its folder."""

    name: str
    version: str
    folder: str


class ConstraintsError(ValueError):
    """A line or marker of a constraints file that this script cannot read."""


def key(name: str) -> str:
    """Return a package name in the normalized form that pip compares, as PEP 503 defines it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _numbers(version: str) -> tuple[int, ...]:
    """Return the leading numbers of a version, such as (3, 10, 12) for 3.10.12rc1."""
    found = _NUMBERS.match(version)
    if not found:
        raise ConstraintsError(f"{version!r} is not a version")
    return tuple(int(part) for part in found[0].split("."))


def marker_applies(marker: str, environment: Mapping[str, str]) -> bool:
    """Return whether a marker holds in an environment. It reads only `name op "value"` clauses joined by `and`."""
    applies = True
    for clause in re.split(r"\s+and\s+", marker.strip()):
        found = _CLAUSE.fullmatch(clause.strip())
        if not found or found["name"] not in environment:
            raise ConstraintsError(f"cannot read the marker {marker!r}")
        actual, wanted, compare = environment[found["name"]], found["value"], _OPERATORS[found["op"]]
        if found["name"] in VERSION_NAMES:
            left, right = _numbers(actual), _numbers(wanted)
            width = max(len(left), len(right))
            applies = compare(left + (0,) * (width - len(left)), right + (0,) * (width - len(right))) and applies
        elif found["op"] in ("==", "!="):
            applies = compare(actual, wanted) and applies
        else:
            raise ConstraintsError(f"cannot compare {found['name']} with {found['op']} in the marker {marker!r}")
    return applies


def set_versions(text: str, environment: Mapping[str, str]) -> dict[str, str]:
    """Return the version that a constraints file sets for each package in an environment, by normalized name."""
    versions: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        found = _LINE.fullmatch(line)
        if not found:
            raise ConstraintsError(f"line {number} is not a name and an exact version: {line}")
        if found["marker"] and not marker_applies(found["marker"], environment):
            continue
        name = key(found["name"])
        if name in versions:
            raise ConstraintsError(f"line {number} sets a second version of {found['name']}")
        versions[name] = found["version"]
    return versions


def problems(installed: Iterable[Package], versions: Mapping[str, str], skipped: Iterable[str] = ()) -> list[str]:
    """Return a line for each installed package that the versions lack or set to another version.

    skipped names the packages that the constraints file leaves out on purpose.
    """
    skip = {key(name) for name in skipped}
    found: list[str] = []
    for package in sorted(installed):
        if key(package.name) in skip:
            continue
        wanted = versions.get(key(package.name))
        where = f"{package.name or '(no name)'} {package.version or '(no version)'} in {package.folder}"
        if wanted is None:
            found.append(f"{where}: constraints.txt lacks it")
        elif package.version != wanted:
            found.append(f"{where}: constraints.txt sets {wanted}")
    return found


def installed_packages(folders: Iterable[Path] | None = None) -> list[Package]:
    """Return the distributions in the folders, or in every folder of sys.path when folders is None."""
    found = metadata.distributions() if folders is None else metadata.distributions(path=[str(f) for f in folders])
    return [
        Package(dist.metadata.get("Name") or "", dist.metadata.get("Version") or "", str(dist.locate_file("")))
        for dist in found
    ]


def environment() -> dict[str, str]:
    """Return the values of the markers that set_versions reads, for the Python that runs this script."""
    return {
        "python_version": ".".join(platform.python_version_tuple()[:2]),
        "python_full_version": platform.python_version(),
        "sys_platform": sys.platform,
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "os_name": os.name,
        "implementation_name": sys.implementation.name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", action="append", type=Path, help="check only the packages in this folder")
    parser.add_argument("--skip", action="append", default=[], metavar="NAME", help="a package the file leaves out")
    parser.add_argument("--constraints", type=Path, default=ROOT / "constraints.txt")
    args = parser.parse_args(argv)
    try:
        versions = set_versions(args.constraints.read_text(encoding="utf-8"), environment())
    except (OSError, UnicodeDecodeError, ConstraintsError) as error:
        print(f"installcheck: {args.constraints}: {error}")
        return 1
    installed = installed_packages(args.folder)
    found = problems(installed, versions, args.skip)
    for problem in found:
        print(problem)
    print(f"installcheck: {len(installed)} packages, {len(found)} problems")
    if not installed:
        print("installcheck: no package found, so nothing was checked")
        return 1
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
