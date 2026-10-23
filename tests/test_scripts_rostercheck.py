from __future__ import annotations

import ast

import pytest

import rostercheck
from gitrepo import make_repo
from sources import Problem

AGENTS_MD = """# Rules

## Module map

| Module | What it holds |
| --- | --- |
| `main.py` | entry |
| `settings.py` | settings |
| `gui.py` | GUI |
| `ui/` | GUI parts |
| `version.py` | version |
| `pkg/` | package |
| `docs/` | docs |

## What every change must pass

Run `scancheck.py` and `othercheck.py`. They read `main.py`.

## Prose
"""
SETTINGS_PY = """from typing import TypedDict

class SettingsFile(TypedDict):
    proxy: str
    dark_mode: bool

default_settings: SettingsFile = {
    "proxy": "",
    "dark_mode": False,
}

class Settings:
    log: bool
    proxy: str
    dark_mode: bool

    def alter(self) -> None:
        pass
"""
GUI_PY = """class Panel:
    def __init__(self, manager):
        self._settings = manager._twitch.settings
        self.dark = self._settings.dark_mode
        manager._twitch.settings.alter()
"""
PROXY_PY = """def proxy_of(settings):
    return settings.proxy
"""
PREVIEW_PY = """from types import SimpleNamespace

def run_preview(manager):
    mock = SimpleNamespace(settings=SimpleNamespace(proxy="", dark_mode=False, alter=lambda: None))
"""
SETTINGS_MD = """# settings

## The keys

| Key | Type |
| --- | --- |
| `proxy` | str |
| `dark_mode` | bool |

## Other

| `extra` | not a key |
"""


def files() -> dict[str, str]:
    return {
        "AGENTS.md": AGENTS_MD,
        "main.py": "",
        "settings.py": SETTINGS_PY,
        "gui.py": GUI_PY,
        "ui/__init__.py": "",
        "ui/proxy.py": PROXY_PY,
        "ui/preview.py": PREVIEW_PY,
        "version.py": "",
        "pkg/__init__.py": "",
        "pkg/inner.py": "",
        "tests/test_x.py": "",
        "docs/modules/main.md": "",
        "docs/modules/settings.md": SETTINGS_MD,
        "docs/modules/gui.md": "",
        "docs/modules/ui.md": "",
        "docs/modules/pkg.md": "",
        "justfile": "check:\n    python scripts/scancheck.py\n    python scripts/othercheck.py\n",
        "scripts/scancheck.py": "",
        "scripts/othercheck.py": "",
        "scripts/sources.py": "",
        "scripts/bannedwords.py": "",
        "scripts/commitlint.py": "",
    }


def problems_with(tmp_path, changes: dict[str, str | None] | None = None) -> list[str]:
    tree = files()
    for name, text in (changes or {}).items():
        tree.pop(name, None)
        if text is not None:
            tree[name] = text
    count, problems = rostercheck.check(make_repo(tmp_path, tree))
    assert count == 5
    return [str(problem) for problem in problems]


def test_check_returns_no_problem_when_every_list_matches_the_code(tmp_path):
    assert problems_with(tmp_path) == []


def test_check_reads_a_missing_file_as_empty(tmp_path):
    assert rostercheck.check(make_repo(tmp_path)) == (5, [Problem("AGENTS.md", 1, "the module map lacks docs/")])


def test_check_reports_a_new_module_missing_from_the_map_and_from_the_module_docs(tmp_path):
    assert problems_with(tmp_path, {"new.py": ""}) == [
        "AGENTS.md:1: the module map lacks new.py",
        "docs/modules/:1: docs/modules/ lacks new.md",
    ]


def test_check_reports_a_deleted_module_still_in_the_map_the_list_of_scans_and_its_doc(tmp_path):
    assert problems_with(tmp_path, {"main.py": None}) == [
        "AGENTS.md:1: the list of scans lists main.py, which does not exist",
        "AGENTS.md:1: the module map lists main.py, which does not exist",
        "docs/modules/:1: docs/modules/ has main.md, which matches no entry of the module map",
    ]


def test_check_reports_a_module_listed_twice_in_the_map(tmp_path):
    agents = AGENTS_MD.replace("| `docs/` | docs |", "| `docs/` | docs |\n| `gui.py` | again |")
    assert problems_with(tmp_path, {"AGENTS.md": agents}) == ["AGENTS.md:1: the module map lists gui.py twice"]


def test_check_reports_a_package_without_a_doc(tmp_path):
    assert problems_with(tmp_path, {"docs/modules/pkg.md": None}) == [
        "docs/modules/:1: docs/modules/ lacks pkg.md"
    ]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"settings.py": SETTINGS_PY.replace('    "dark_mode": False,\n', "")},
         "settings.py:1: default_settings lacks dark_mode"),
        ({"settings.py": SETTINGS_PY.replace('    "proxy": "",\n', '    "proxy": "",\n    "old": 1,\n')},
         "settings.py:1: default_settings lists old, which SettingsFile lacks"),
        ({"settings.py": SETTINGS_PY.replace("    log: bool\n    proxy: str\n    dark_mode: bool\n",
                                             "    log: bool\n    proxy: str\n")},
         "settings.py:1: Settings lacks the attribute dark_mode"),
        ({"docs/modules/settings.md": SETTINGS_MD.replace("| `dark_mode` | bool |\n", "")},
         "docs/modules/settings.md:1: the key table lacks dark_mode"),
        ({"docs/modules/settings.md": SETTINGS_MD.replace("| `proxy` | str |\n", "| `proxy` | str |\n| `old` | x |\n")},
         "docs/modules/settings.md:1: the key table lists old, which SettingsFile lacks"),
        ({"ui/preview.py": PREVIEW_PY.replace(", dark_mode=False", "")},
         "ui/preview.py:1: the settings mock lacks dark_mode, which gui.py reads"),
        ({"ui/preview.py": PREVIEW_PY.replace('proxy="", ', "")},
         "ui/preview.py:1: the settings mock lacks proxy, which ui/proxy.py reads"),
    ],
    ids=[
        "default_settings", "an unknown default", "Settings attributes", "the doc key table", "an unknown doc key",
        "the preview mock", "a read in ui/",
    ],
)
def test_check_reports_a_settings_key_missing_from_one_of_the_four_places(tmp_path, change, problem):
    assert problems_with(tmp_path, change) == [problem]


def test_check_reports_a_settings_method_gui_py_calls_but_the_mock_lacks(tmp_path):
    preview = PREVIEW_PY.replace(", alter=lambda: None", "")
    assert problems_with(tmp_path, {"ui/preview.py": preview}) == [
        "ui/preview.py:1: the settings mock lacks alter, which gui.py reads"
    ]


def test_check_accepts_a_mock_without_a_key_that_gui_py_does_not_read(tmp_path):
    gui = GUI_PY.replace("        self.dark = self._settings.dark_mode\n", "")
    preview = PREVIEW_PY.replace(", dark_mode=False", "")
    assert problems_with(tmp_path, {"gui.py": gui, "ui/preview.py": preview}) == []


def test_check_reports_a_scan_missing_from_the_justfile_and_from_agents_md(tmp_path):
    assert problems_with(tmp_path, {"scripts/newcheck.py": ""}) == [
        "AGENTS.md:1: the list of scans lacks newcheck.py",
        "justfile:1: the justfile lacks newcheck.py",
    ]


def test_check_reports_a_recipe_that_runs_a_script_that_does_not_exist(tmp_path):
    justfile = files()["justfile"] + "    python scripts/gone.py\n"
    assert problems_with(tmp_path, {"justfile": justfile}) == [
        "justfile:1: the justfile names gone.py, which is not a scan in scripts/"
    ]


def test_check_reports_a_helper_script_that_a_recipe_runs_as_a_scan(tmp_path):
    justfile = files()["justfile"] + "    python scripts/commitlint.py\n"
    assert problems_with(tmp_path, {"justfile": justfile}) == [
        "justfile:1: the justfile names commitlint.py, which is not a scan in scripts/"
    ]


@pytest.mark.parametrize(
    ("name", "problems"),
    [
        ("gone.py", ["AGENTS.md:1: the list of scans lists gone.py, which does not exist"]),
        ("inner.py", []),
        ("test_x.py", []),
        ("version.py", []),
        ("commitlint.py", []),
    ],
    ids=[
        "a missing file", "a module inside a package", "a file in tests/", "a top-level module", "a helper in scripts/",
    ],
)
def test_check_reports_a_name_in_the_list_of_scans_that_no_file_in_the_repo_has(tmp_path, name, problems):
    agents = AGENTS_MD.replace("They read `main.py`.", f"They read `main.py` and `{name}`.")
    assert problems_with(tmp_path, {"AGENTS.md": agents}) == problems


def test_check_reads_the_list_of_scans_only_from_its_section_of_agents_md(tmp_path):
    agents = AGENTS_MD.replace("Run `scancheck.py` and `othercheck.py`.", "Run `scancheck.py`.") + "`othercheck.py`\n"
    assert problems_with(tmp_path, {"AGENTS.md": agents}) == ["AGENTS.md:1: the list of scans lacks othercheck.py"]


def test_table_names_returns_the_backticked_first_cells_under_the_heading_only():
    assert rostercheck.table_names(SETTINGS_MD, "The keys") == ["proxy", "dark_mode"]
    assert rostercheck.table_names(SETTINGS_MD, "Other") == ["extra"]
    assert rostercheck.table_names(SETTINGS_MD, "Missing") == []


def test_compare_reports_lacking_unknown_and_repeated_names_in_order():
    assert rostercheck.compare("x.md", "the list", ["b", "z", "b", "y", "y"], {"a", "b", "c"}) == [
        Problem("x.md", 1, "the list lacks a"),
        Problem("x.md", 1, "the list lacks c"),
        Problem("x.md", 1, "the list lists y, which does not exist"),
        Problem("x.md", 1, "the list lists z, which does not exist"),
        Problem("x.md", 1, "the list lists b twice"),
        Problem("x.md", 1, "the list lists y twice"),
    ]


def test_compare_ends_the_problem_for_an_unknown_name_with_the_given_text():
    assert rostercheck.compare("x.md", "the list", ["a", "z"], {"a"}, "has {}, for nothing") == [
        Problem("x.md", 1, "the list has z, for nothing")
    ]


def test_modules_returns_top_level_modules_and_packages_only():
    names = ["a.py", "build.spec", "pkg/__init__.py", "pkg/b.py", "pkg/sub/__init__.py", "scripts/c.py", "README.md"]
    assert rostercheck.modules(names) == {"a.py", "pkg/"}


def test_class_body_returns_an_empty_list_for_a_missing_class():
    module = ast.parse("class A:\n    x: int\n")
    assert rostercheck.annotated(rostercheck.class_body(module, "A")) == ["x"]
    assert rostercheck.class_body(module, "B") == []


def test_annotated_returns_only_annotated_names():
    body = ast.parse("class A:\n    x: int\n    y = 1\n    z: str = 'a'\n    def f(self): pass\n").body[0].body
    assert rostercheck.annotated(body) == ["x", "z"]


def test_default_keys_returns_the_keys_of_the_annotated_dict_or_nothing():
    assert rostercheck.default_keys(ast.parse(SETTINGS_PY)) == ["proxy", "dark_mode"]
    assert rostercheck.default_keys(ast.parse("default_settings: dict = dict(a=1)\n")) == []
    assert rostercheck.default_keys(ast.parse("other: dict = {'a': 1}\n")) == []


def test_mock_and_reads_returns_the_mock_keywords_and_only_the_reads_from_a_settings_object():
    gui = GUI_PY + PROXY_PY + PREVIEW_PY + "\nclass Row:\n    def draw(self, widget):\n        return self.dark_mode, widget.log\n"
    mock, reads = rostercheck.mock_and_reads(ast.parse(gui), {"proxy", "dark_mode", "alter", "log"})
    assert mock == ["proxy", "dark_mode", "alter"]
    assert reads == {"proxy", "dark_mode", "alter"}


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path)
    assert rostercheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == "AGENTS.md:1: the module map lacks docs/\nrostercheck: 5 lists, 1 problems\n"


def test_main_returns_0_when_every_list_matches(tmp_path, capsys):
    root = make_repo(tmp_path, files())
    assert rostercheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "rostercheck: 5 lists, 0 problems\n"
