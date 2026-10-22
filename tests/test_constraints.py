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
# The commit of appimage-builder that the AppImage job installs, and the requirements in its setup.py.
APPIMAGE_BUILDER_COMMIT = "1a8794d3c89f288fbd82b9accd7c0b74611147d5"
APPIMAGE_BUILDER_REQUIRES = (
    "PyYAML", "docker", "requests", "schema", "packaging", "questionary", "emrichen", "ruamel.yaml", "roam",
    "urllib3", "lief", "python-gnupg", "libconf", "pydpkg",
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


def test_the_appimage_job_installs_the_commit_whose_requirements_are_listed():
    arguments = [argument for _, command in install_commands() for argument in command]

    assert [argument for argument in arguments if argument.startswith("git+")] == [
        f"git+https://github.com/AppImageCrafters/appimage-builder.git@{APPIMAGE_BUILDER_COMMIT}"
    ]


def test_every_package_that_appimage_builder_requires_has_a_line_in_constraints_txt():
    assert sorted({key(name) for name in APPIMAGE_BUILDER_REQUIRES} - listed_packages()) == []
