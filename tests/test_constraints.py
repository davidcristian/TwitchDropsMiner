from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The files whose commands install the packages of a build.
INSTALLERS = (
    ".github/workflows/ci.yml",
    "appimage/AppImageBuilder.yml",
    "setup_env.sh",
    "setup_env.bat",
    "build.sh",
    "build.bat",
)
INSTALL = re.compile(r"""\bpip"?\s+install\s(.*)""")
TOKEN = re.compile(r'"[^"]*"|\S+')
EXACT = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.!+]*)(\s*;\s*\S.*)?")


def key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def lines_without_comments(name: str) -> list[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [line.split("#", 1)[0].strip() for line in lines if line.split("#", 1)[0].strip()]


def install_commands() -> list[tuple[str, list[str]]]:
    commands = []
    for name in INSTALLERS:
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            found = INSTALL.search(line)
            if found and not line.lstrip().startswith(("#", "REM ")):
                commands.append((name, [token.strip('"') for token in TOKEN.findall(found[1])]))
    return commands


def named_packages(arguments: list[str]) -> list[str]:
    names = []
    skip = False
    for argument in arguments:
        if skip:
            skip = False
        elif argument in ("-c", "-r", "--build-constraint"):
            skip = True
        elif not argument.startswith(("-", "git+")):
            names.append(argument)
    return names


def reads_constraints(arguments: list[str]) -> bool:
    return any(first == "-c" and second.endswith("constraints.txt") for first, second in zip(arguments, arguments[1:]))


def listed_packages() -> set[str]:
    return {key(EXACT.fullmatch(line)[1]) for line in lines_without_comments("constraints.txt")}


def test_every_line_of_constraints_txt_is_a_name_and_an_exact_version():
    lines = lines_without_comments("constraints.txt")

    assert lines
    assert [line for line in lines if not EXACT.fullmatch(line)] == []


def test_every_pip_install_of_a_build_reads_constraints_txt():
    commands = install_commands()

    assert {name for name, _ in commands} == set(INSTALLERS)
    assert [(name, " ".join(arguments)) for name, arguments in commands if not reads_constraints(arguments)] == []


def test_every_package_that_a_build_names_has_a_line_in_constraints_txt():
    named = {key(package) for _, arguments in install_commands() for package in named_packages(arguments)}
    required = {key(re.match(r"[A-Za-z0-9._-]+", line)[0]) for line in lines_without_comments("requirements.txt")}

    assert {"pip", "pyinstaller", "pygobject"} <= named | required
    assert sorted((named | required) - listed_packages()) == []
