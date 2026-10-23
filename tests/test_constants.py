from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

import constants


def load_constants(
    argv0: Path,
    appimage: Path | None = None,
    platform: str = "linux",
    appdir: Path | str | None = None,
    source: Path | None = None,
) -> ModuleType:
    # A second copy of the module runs its import time code with test inputs. A reload of `constants` would
    # replace the classes that other modules and tests already hold.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", [str(argv0)])
        patch.setattr(sys, "platform", platform)
        patch.delattr(sys, "_MEIPASS", raising=False)
        for name, value in (("APPIMAGE", appimage), ("APPDIR", appdir)):
            if value is None:
                patch.delenv(name, raising=False)
            else:
                patch.setenv(name, str(value))
        spec = importlib.util.spec_from_file_location("constants_copy", source or constants.__file__)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def mounted_appimage(tmp_path: Path) -> tuple[Path, Path]:
    appimage = tmp_path / "apps" / "TwitchDropsMiner.AppImage"
    appimage.parent.mkdir()
    appimage.touch()
    src = tmp_path / "mount" / "usr" / "src"
    src.mkdir(parents=True)
    shutil.copy(constants.__file__, src / "constants.py")
    return appimage, src


def test_resource_path_from_source_is_under_the_working_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", False)
    monkeypatch.setattr(constants, "IS_PACKAGED", False)
    monkeypatch.setattr(constants, "WORKING_DIR", tmp_path)
    assert constants._resource_path("lang") == tmp_path / "lang"
    assert constants._resource_path(Path("icons", "pickaxe.ico")) == tmp_path / "icons" / "pickaxe.ico"


def test_resource_path_in_a_pyinstaller_build_is_under_the_unpack_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", False)
    monkeypatch.setattr(constants, "IS_PACKAGED", True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI1234"), raising=False)
    assert constants._resource_path("lang") == tmp_path / "_MEI1234" / "lang"


def test_resource_path_in_an_appimage_is_next_to_the_started_script(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", True)
    monkeypatch.setattr(constants, "IS_PACKAGED", True)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "usr" / "src" / "main.py")])
    assert constants._resource_path("lang") == tmp_path / "usr" / "src" / "lang"


@pytest.mark.parametrize("started", ["main.py", "TwitchDropsMiner.exe", "TwitchDropsMiner"])
def test_the_app_keeps_its_files_in_the_folder_of_the_started_file(tmp_path, started):
    copy = load_constants(tmp_path / "app" / started)
    assert copy.SELF_PATH == tmp_path / "app" / started
    assert copy.WORKING_DIR == tmp_path / "app"
    assert copy.SETTINGS_PATH == tmp_path / "app" / "settings.json"
    assert copy.COOKIES_PATH == tmp_path / "app" / "cookies.jar"
    assert copy.CACHE_DB == tmp_path / "app" / "cache" / "mapping.json"
    assert copy.LANG_PATH == tmp_path / "app" / "lang"
    assert not copy.IS_PACKAGED


@pytest.mark.parametrize("started", ["gui.py", "pyinstaller"])
def test_the_gui_preview_and_pyinstaller_use_main_py_next_to_constants(tmp_path, started):
    copy = load_constants(tmp_path / "bin" / started)
    repo = Path(constants.__file__).resolve().parent
    assert copy.SELF_PATH == repo / "main.py"
    assert copy.WORKING_DIR == repo


def test_an_appimage_keeps_its_files_next_to_the_appimage_file(tmp_path):
    appimage, src = mounted_appimage(tmp_path)
    copy = load_constants(src / "main.py", appimage, appdir=tmp_path / "mount", source=src / "constants.py")
    assert copy.IS_APPIMAGE and copy.IS_PACKAGED
    assert copy.SELF_PATH == appimage
    assert copy.WORKING_DIR == tmp_path / "apps"
    assert copy.COOKIES_PATH == tmp_path / "apps" / "cookies.jar"
    assert copy.LANG_PATH == src / "lang"


@pytest.mark.parametrize("through_link", ["appdir", "module"])
def test_an_appimage_reached_through_a_symlink_keeps_its_files_next_to_the_appimage_file(tmp_path, through_link):
    appimage, src = mounted_appimage(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "mount", target_is_directory=True)
    appdir, source = (link, src) if through_link == "appdir" else (tmp_path / "mount", link / "usr" / "src")
    copy = load_constants(source / "main.py", appimage, appdir=appdir, source=source / "constants.py")
    assert copy.IS_APPIMAGE and copy.IS_PACKAGED
    assert copy.WORKING_DIR == tmp_path / "apps"


def test_an_appimage_variable_naming_a_missing_file_is_ignored(tmp_path):
    _, src = mounted_appimage(tmp_path)
    copy = load_constants(
        src / "main.py", tmp_path / "gone.AppImage", appdir=tmp_path / "mount", source=src / "constants.py"
    )
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.WORKING_DIR == src


def test_a_run_from_source_started_from_another_appimage_keeps_its_files_in_the_repo(tmp_path):
    other = tmp_path / "apps" / "Editor.AppImage"
    other.parent.mkdir()
    other.touch()
    # the AppImage runtime sets APPDIR to the mounted image, and the editor's terminal passes both on
    copy = load_constants(tmp_path / "repo" / "main.py", other, appdir=tmp_path / "mount_editor")
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.COOKIES_PATH == tmp_path / "repo" / "cookies.jar"


@pytest.mark.parametrize("appdir", [None, ""])
def test_an_appimage_variable_without_appdir_counts_as_a_run_from_source(tmp_path, monkeypatch, appdir):
    appimage, src = mounted_appimage(tmp_path)
    monkeypatch.chdir(src)
    copy = load_constants(src / "main.py", appimage, appdir=appdir, source=src / "constants.py")
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.COOKIES_PATH == src / "cookies.jar"


@pytest.mark.parametrize(("platform", "scripts"), [("win32", "Scripts"), ("linux", "bin"), ("darwin", "bin")])
def test_the_venv_scripts_folder_follows_the_platform(tmp_path, platform, scripts):
    copy = load_constants(tmp_path / "main.py", platform=platform)
    assert copy.SCRIPTS_PATH == tmp_path / "env" / scripts
