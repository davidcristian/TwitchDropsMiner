from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = Path(__file__).resolve().parent.parent / "build.spec"
ICONS = ("pickaxe", "active", "idle", "error", "maint")


def run_spec(spec_dir: Path, monkeypatch) -> dict:
    # build.spec adds its folder to sys.path
    monkeypatch.setattr(sys, "path", list(sys.path))
    options: dict = {}

    def analysis(scripts, **kwargs):
        options.update(kwargs)
        return SimpleNamespace(binaries=[], datas=[], pure=[], scripts=[])

    def target(*args, **kwargs):
        return SimpleNamespace()

    namespace = {"SPECPATH": str(spec_dir), "Analysis": analysis}
    namespace.update(dict.fromkeys(("PYZ", "EXE", "COLLECT", "BUNDLE"), target))
    exec(compile(SPEC.read_bytes(), str(SPEC), "exec"), namespace)
    return options


@pytest.fixture
def spec_dir(tmp_path):
    (tmp_path / "icons").mkdir()
    for name in ICONS:
        (tmp_path / "icons" / f"{name}.ico").touch()
    (tmp_path / "lang").mkdir()
    (tmp_path / "lang" / "English.json").write_text("{}", encoding="utf-8")
    return tmp_path


def add_translations(spec_dir: Path, *names: str) -> None:
    for name in names:
        (spec_dir / "lang" / f"{name}.json").write_text("{}", encoding="utf-8")


def test_the_build_bundles_the_files_next_to_the_spec_from_any_folder(spec_dir, tmp_path_factory, monkeypatch):
    add_translations(spec_dir, "Polski", "Deutsch")
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))

    datas = run_spec(spec_dir, monkeypatch)["datas"]

    assert sorted(path for path, dest in datas if dest == "lang") == [
        spec_dir / "lang" / "Deutsch.json",
        spec_dir / "lang" / "Polski.json",
    ]
    assert [path.name for path, dest in datas if dest == "./icons"] == [f"{name}.ico" for name in ICONS]


def test_the_build_fails_when_lang_has_only_english(spec_dir, monkeypatch):
    with pytest.raises(FileNotFoundError, match="No translation file"):
        run_spec(spec_dir, monkeypatch)


def test_the_build_fails_when_an_icon_is_missing(spec_dir, monkeypatch):
    add_translations(spec_dir, "Polski")
    (spec_dir / "icons" / "idle.ico").unlink()

    with pytest.raises(FileNotFoundError, match="idle.ico"):
        run_spec(spec_dir, monkeypatch)


def test_the_build_adds_no_setuptools_module(spec_dir, monkeypatch):
    add_translations(spec_dir, "Polski")

    hidden = run_spec(spec_dir, monkeypatch)["hiddenimports"]

    assert "PIL._tkinter_finder" in hidden
    assert [name for name in hidden if name.split(".")[0] in ("setuptools", "distutils")] == []


def test_the_linux_build_bundles_each_typelib_that_the_tray_icon_requires(spec_dir, monkeypatch):
    add_translations(spec_dir, "Polski")
    monkeypatch.setattr(sys, "platform", "linux")

    typelibs = [path for path, dest in run_spec(spec_dir, monkeypatch)["datas"] if dest == "gi_typelibs"]

    assert sorted(path.name for path in typelibs) == ["AyatanaAppIndicator3-0.1.typelib", "DBus-1.0.typelib"]
    assert len({path.parent for path in typelibs}) == 1
