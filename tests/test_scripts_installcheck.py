from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import installcheck
from installcheck import ConstraintsError, Package

SCRIPT = Path(installcheck.__file__)
LINUX_310 = {"python_version": "3.10", "python_full_version": "3.10.12", "sys_platform": "linux"}
WINDOWS_314 = {"python_version": "3.14", "python_full_version": "3.14.0", "sys_platform": "win32"}
PILLOW = 'Pillow==12.3.0; python_version < "3.11"\nPillow==13.0.0; python_version >= "3.11"\n'


def install(folder: Path, name: str, version: str) -> None:
    info = folder / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "normalized"),
    [("aiohttp", "aiohttp"), ("PyGObject", "pygobject"), ("ruamel.yaml", "ruamel-yaml"), ("A_-.b", "a-b")],
)
def test_key_lowers_a_name_and_joins_each_run_of_dots_dashes_and_underscores(name, normalized):
    assert installcheck.key(name) == normalized


@pytest.mark.parametrize(
    ("marker", "environment", "applies"),
    [
        ('python_version < "3.11"', LINUX_310, True),
        ('python_version < "3.11"', WINDOWS_314, False),
        ("python_version >= '3.9'", LINUX_310, True),
        ('python_full_version == "3.14"', WINDOWS_314, True),
        ('python_full_version >= "3.10.13"', LINUX_310, False),
        ('python_full_version > "3.10"', LINUX_310, True),
        ('sys_platform == "win32"', WINDOWS_314, True),
        ('sys_platform != "win32"', WINDOWS_314, False),
        ('python_version >= "3.10" and sys_platform == "linux"', LINUX_310, True),
        ('python_version >= "3.10"  and  sys_platform == "win32"', LINUX_310, False),
    ],
    ids=[
        "older python",
        "newer python",
        "3.10 is not below 3.9 as text would be",
        "3.14 equals 3.14.0",
        "full version",
        "3.10.12 is above 3.10",
        "platform equal",
        "platform not equal",
        "and of two true clauses",
        "and with one false clause",
    ],
)
def test_marker_applies_compares_versions_as_numbers_and_other_names_as_text(marker, environment, applies):
    assert installcheck.marker_applies(marker, environment) is applies


@pytest.mark.parametrize(
    "marker",
    [
        'python_version < "3.11" or sys_platform == "linux"',
        '(python_version < "3.11")',
        'platform_release == "6.6"',
        'sys_platform < "win32"',
        'python_version >= "three"',
        'python_version < "3.0" and implementation_version == "3"',
        "python_version < 3.11",
    ],
    ids=["or", "parentheses", "unknown name", "ordering of text", "not a version", "after a false clause", "no quotes"],
)
def test_marker_applies_raises_for_a_marker_it_cannot_read(marker):
    with pytest.raises(ConstraintsError):
        installcheck.marker_applies(marker, LINUX_310)


def test_set_versions_reads_each_line_by_normalized_name_and_skips_comments_and_blank_lines():
    text = "# a comment\n\nruamel.yaml==0.19.1\nPyGObject == 3.50.2  # built from source\n"

    assert installcheck.set_versions(text, LINUX_310) == {"ruamel-yaml": "0.19.1", "pygobject": "3.50.2"}


def test_set_versions_returns_nothing_for_an_empty_file():
    assert installcheck.set_versions("", LINUX_310) == {}


@pytest.mark.parametrize(("environment", "version"), [(LINUX_310, "12.3.0"), (WINDOWS_314, "13.0.0")])
def test_set_versions_keeps_only_the_line_whose_marker_holds(environment, version):
    assert installcheck.set_versions(PILLOW, environment) == {"pillow": version}


def test_set_versions_leaves_out_a_package_whose_only_line_has_a_false_marker():
    assert installcheck.set_versions('pywin32==312; sys_platform == "win32"\n', LINUX_310) == {}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("pip==26.2.1\naiohttp>=3.9\n", "line 2 is not a name and an exact version: aiohttp>=3.9"),
        ("aiohttp\n", "line 1 is not a name and an exact version: aiohttp"),
        ("Pillow==12.3.0\npillow==13.0.0\n", "line 2 sets a second version of pillow"),
        ('pip==26.2.1; python_version or "3"\n', "cannot read the marker"),
    ],
    ids=["a range", "no version", "two lines that both apply", "an unreadable marker"],
)
def test_set_versions_raises_for_a_line_it_cannot_read(text, message):
    with pytest.raises(ConstraintsError, match=message):
        installcheck.set_versions(text, LINUX_310)


def test_problems_returns_nothing_when_each_package_has_its_version_under_any_spelling():
    installed = [Package("typing_extensions", "4.16.0", "/site"), Package("PIP", "26.2.1", "/site")]

    assert installcheck.problems(installed, {"typing-extensions": "4.16.0", "pip": "26.2.1"}) == []


def test_problems_reports_a_package_the_file_lacks_and_one_at_another_version_sorted_by_name():
    installed = [Package("yarl", "1.25.2", "/site"), Package("colorama", "0.4.6", "/user")]

    assert installcheck.problems(installed, {"yarl": "1.25.1"}) == [
        "colorama 0.4.6 in /user: constraints.txt lacks it",
        "yarl 1.25.2 in /site: constraints.txt sets 1.25.1",
    ]


def test_problems_leaves_out_a_skipped_package_under_any_spelling():
    installed = [Package("appimage_builder", "1.1.1.dev0", "/user"), Package("pip", "26.2.1", "/user")]

    assert installcheck.problems(installed, {"pip": "26.2.1"}, ["AppImage-Builder"]) == []


def test_problems_reports_a_package_whose_metadata_has_no_name_or_version():
    installed = [Package("", "", "/site"), Package("pip", "", "/site")]

    assert installcheck.problems(installed, {"pip": "26.2.1"}) == [
        "(no name) (no version) in /site: constraints.txt lacks it",
        "pip (no version) in /site: constraints.txt sets 26.2.1",
    ]


def test_installed_packages_reads_the_dist_info_and_egg_info_folders_of_each_folder(tmp_path):
    install(tmp_path / "user", "pip", "26.2.1")
    install(tmp_path / "appdir", "Pillow", "12.3.0")
    egg = tmp_path / "appdir" / "six-1.16.0.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("Metadata-Version: 1.1\nName: six\nVersion: 1.16.0\n", encoding="utf-8")

    found = installcheck.installed_packages([tmp_path / "user", tmp_path / "appdir"])

    assert sorted(found) == [
        Package("Pillow", "12.3.0", str(tmp_path / "appdir")),
        Package("pip", "26.2.1", str(tmp_path / "user")),
        Package("six", "1.16.0", str(tmp_path / "appdir")),
    ]


def test_installed_packages_returns_an_empty_name_and_version_for_metadata_without_them(tmp_path):
    (tmp_path / "broken-1.0.dist-info").mkdir()

    assert installcheck.installed_packages([tmp_path]) == [Package("", "", str(tmp_path))]


@pytest.mark.parametrize("folder", ["empty", "missing"])
def test_installed_packages_returns_nothing_for_an_empty_or_missing_folder(tmp_path, folder):
    (tmp_path / "empty").mkdir()

    assert installcheck.installed_packages([tmp_path / folder]) == []


def test_installed_packages_reads_every_folder_of_sys_path_without_folders():
    names = {installcheck.key(package.name) for package in installcheck.installed_packages()}

    assert {"pytest", "ruff"} <= names


def test_environment_describes_the_python_that_runs_it():
    environment = installcheck.environment()

    assert environment["python_version"] == f"{sys.version_info[0]}.{sys.version_info[1]}"
    assert environment["sys_platform"] == sys.platform
    assert installcheck.set_versions(PILLOW, environment) == {
        "pillow": "12.3.0" if sys.version_info < (3, 11) else "13.0.0"
    }


def test_main_returns_0_when_each_package_has_the_version_in_the_file(tmp_path, capsys):
    install(tmp_path / "site", "pip", "26.2.1")
    install(tmp_path / "site", "appimage-builder", "1.1.1.dev0")
    (tmp_path / "constraints.txt").write_text("pip==26.2.1\n", encoding="utf-8")
    folder, constraints = str(tmp_path / "site"), str(tmp_path / "constraints.txt")

    code = installcheck.main(["--folder", folder, "--constraints", constraints, "--skip", "appimage-builder"])

    assert (code, capsys.readouterr().out) == (0, "installcheck: 2 packages, 0 problems\n")


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    install(tmp_path / "site", "pip", "26.2.2")
    install(tmp_path / "site", "colorama", "0.4.6")
    (tmp_path / "constraints.txt").write_text("pip==26.2.1\n", encoding="utf-8")

    code = installcheck.main(["--folder", str(tmp_path / "site"), "--constraints", str(tmp_path / "constraints.txt")])

    assert (code, capsys.readouterr().out.splitlines()) == (
        1,
        [
            f"colorama 0.4.6 in {tmp_path / 'site'}: constraints.txt lacks it",
            f"pip 26.2.2 in {tmp_path / 'site'}: constraints.txt sets 26.2.1",
            "installcheck: 2 packages, 2 problems",
        ],
    )


def test_main_returns_1_when_the_folder_has_no_package(tmp_path, capsys):
    (tmp_path / "constraints.txt").write_text("pip==26.2.1\n", encoding="utf-8")

    code = installcheck.main(["--folder", str(tmp_path / "none"), "--constraints", str(tmp_path / "constraints.txt")])

    assert (code, capsys.readouterr().out.splitlines()) == (
        1,
        ["installcheck: 0 packages, 0 problems", "installcheck: no package found, so nothing was checked"],
    )


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "No such file"), (b"pip>=26\n", "line 1 is not a name"), (b"\xff\xfe\n", "can't decode")],
    ids=["missing file", "a range", "not UTF-8"],
)
def test_main_returns_1_when_it_cannot_read_the_constraints_file(tmp_path, capsys, content, message):
    install(tmp_path / "site", "pip", "26.2.1")
    if content is not None:
        (tmp_path / "constraints.txt").write_bytes(content)

    code = installcheck.main(["--folder", str(tmp_path / "site"), "--constraints", str(tmp_path / "constraints.txt")])

    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith(f"installcheck: {tmp_path / 'constraints.txt'}: ")
    assert message in out


def test_the_script_runs_from_any_folder_and_reads_the_repo_constraints_file_by_default(tmp_path):
    install(tmp_path / "site", "pip", "0.0.1")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--folder", str(tmp_path / "site")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (result.returncode, result.stdout.splitlines()[-1]) == (1, "installcheck: 1 packages, 1 problems")
    assert ": constraints.txt sets " in result.stdout
