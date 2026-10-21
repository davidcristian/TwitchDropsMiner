import errno
from functools import partial
from pathlib import Path

import pytest

from savefiles import UnsavedChanges, replace_file, save_each


class FakeFile:
    def __init__(self, name: str, written: list[str], error: Exception | None = None) -> None:
        self._name = name
        self._written = written
        self._error = error

    def save(self) -> None:
        if self._error is not None:
            raise self._error
        self._written.append(self._name)


def test_save_each_runs_every_save_in_order_and_reports_nothing():
    written: list[str] = []
    reported: list[OSError] = []
    files = [FakeFile("mapping.json", written), FakeFile("settings.json", written)]
    save_each([file.save for file in files], reported.append)
    assert written == ["mapping.json", "settings.json"]
    assert reported == []


def test_save_each_reports_a_full_disk_and_runs_the_next_save():
    written: list[str] = []
    reported: list[OSError] = []
    full = OSError(errno.ENOSPC, "No space left on device")
    files = [FakeFile("mapping.json", written, full), FakeFile("settings.json", written)]
    save_each([file.save for file in files], reported.append)
    assert reported == [full]
    assert written == ["settings.json"]


def test_save_each_reports_every_failed_save_in_order():
    written: list[str] = []
    reported: list[OSError] = []
    held = PermissionError(errno.EACCES, "Access is denied")
    full = OSError(errno.ENOSPC, "No space left on device")
    files = [FakeFile("mapping.json", written, held), FakeFile("settings.json", written, full)]
    save_each([file.save for file in files], reported.append)
    assert reported == [held, full]
    assert written == []


def test_save_each_passes_up_an_error_that_is_not_an_oserror_and_stops():
    written: list[str] = []
    reported: list[OSError] = []
    unknown_type = TypeError("Object of type Game is not JSON serializable")
    files = [FakeFile("mapping.json", written, unknown_type), FakeFile("settings.json", written)]
    with pytest.raises(TypeError):
        save_each([file.save for file in files], reported.append)
    assert reported == []
    assert written == []


class FakeSaver:
    def __init__(self, contents: bytes, error: Exception | None = None) -> None:
        self.contents = contents
        self.error = error
        self.paths: list[Path] = []

    def save(self, path: Path) -> None:
        self.paths.append(path)
        if self.error is None:
            path.write_bytes(self.contents)
            return
        path.write_bytes(self.contents[: len(self.contents) // 2])
        raise self.error


def test_replace_file_writes_a_second_file_in_the_same_folder_then_replaces_the_old_one(tmp_path):
    path = tmp_path / "cookies.jar"
    path.write_bytes(b"old login")
    saver = FakeSaver(b"new login")
    replace_file(path, saver.save)
    assert saver.paths == [tmp_path / "cookies.jar.new"]
    assert path.read_bytes() == b"new login"
    assert sorted(tmp_path.iterdir()) == [path]


def test_replace_file_creates_the_file_when_none_exists(tmp_path):
    path = tmp_path / "cookies.jar"
    replace_file(path, FakeSaver(b"first login").save)
    assert path.read_bytes() == b"first login"
    assert sorted(tmp_path.iterdir()) == [path]


def test_replace_file_keeps_the_old_file_when_the_write_stops_halfway(tmp_path):
    path = tmp_path / "cookies.jar"
    path.write_bytes(b"old login")
    full = OSError(errno.ENOSPC, "No space left on device")
    with pytest.raises(OSError) as raised:
        replace_file(path, FakeSaver(b"new login with more cookies", full).save)
    assert raised.value is full
    assert path.read_bytes() == b"old login"
    assert sorted(tmp_path.iterdir()) == [path]


def test_replace_file_leaves_no_file_when_the_first_write_fails(tmp_path):
    path = tmp_path / "cookies.jar"
    with pytest.raises(OSError):
        replace_file(path, FakeSaver(b"first login", OSError(errno.ENOSPC, "No space left on device")).save)
    assert list(tmp_path.iterdir()) == []


def test_replace_file_deletes_the_second_file_when_the_rename_fails(tmp_path):
    path = tmp_path / "cookies.jar"
    path.mkdir()
    (path / "inside").write_bytes(b"kept")
    with pytest.raises(OSError):
        replace_file(path, FakeSaver(b"new login").save)
    assert (path / "inside").read_bytes() == b"kept"
    assert sorted(tmp_path.iterdir()) == [path]


def test_replace_file_passes_up_an_error_that_is_not_an_oserror_and_keeps_the_old_file(tmp_path):
    path = tmp_path / "cookies.jar"
    path.write_bytes(b"old login")
    with pytest.raises(TypeError):
        replace_file(path, FakeSaver(b"new login", TypeError("cannot write this value")).save)
    assert path.read_bytes() == b"old login"
    assert sorted(tmp_path.iterdir()) == [path]


def test_replace_file_writes_over_a_second_file_left_by_a_killed_save(tmp_path):
    path = tmp_path / "cookies.jar"
    path.write_bytes(b"old login")
    (tmp_path / "cookies.jar.new").write_bytes(b"cut")
    replace_file(path, FakeSaver(b"new login").save)
    assert path.read_bytes() == b"new login"
    assert sorted(tmp_path.iterdir()) == [path]


def test_save_each_with_replace_file_reports_a_full_disk_and_keeps_the_old_file(tmp_path):
    path = tmp_path / "cookies.jar"
    path.write_bytes(b"old login")
    full = OSError(errno.ENOSPC, "No space left on device")
    reported: list[OSError] = []
    save_each([partial(replace_file, path, FakeSaver(b"new login", full).save)], reported.append)
    assert reported == [full]
    assert path.read_bytes() == b"old login"


class WriteCounter:
    def __init__(self, error: Exception | None = None) -> None:
        self.writes = 0
        self.error = error

    def write(self) -> None:
        if self.error is not None:
            raise self.error
        self.writes += 1


def test_unsaved_changes_writes_nothing_without_a_change():
    file = WriteCounter()
    changes = UnsavedChanges(file.write)
    changes.save()
    assert file.writes == 0
    assert changes.pending is False


def test_unsaved_changes_writes_a_change_once():
    file = WriteCounter()
    changes = UnsavedChanges(file.write)
    changes.mark()
    changes.save()
    changes.save()
    changes.save()
    assert file.writes == 1
    assert changes.pending is False


def test_unsaved_changes_writes_a_later_change_again():
    file = WriteCounter()
    changes = UnsavedChanges(file.write)
    changes.mark()
    changes.save()
    changes.mark()
    changes.mark()
    changes.save()
    assert file.writes == 2


def test_unsaved_changes_force_writes_without_a_change_and_clears_a_change():
    file = WriteCounter()
    changes = UnsavedChanges(file.write)
    changes.save(force=True)
    assert file.writes == 1
    changes.mark()
    changes.save(force=True)
    changes.save()
    assert file.writes == 2


def test_unsaved_changes_keeps_the_change_after_a_failed_write():
    file = WriteCounter(OSError(errno.ENOSPC, "No space left on device"))
    changes = UnsavedChanges(file.write)
    changes.mark()
    with pytest.raises(OSError):
        changes.save()
    assert changes.pending is True
    file.error = None
    changes.save()
    assert file.writes == 1
    assert changes.pending is False


def test_unsaved_changes_after_save_each_reports_a_full_disk_and_writes_at_the_next_save():
    full = OSError(errno.ENOSPC, "No space left on device")
    file = WriteCounter(full)
    reported: list[OSError] = []
    changes = UnsavedChanges(file.write)
    changes.mark()
    save_each([changes.save], reported.append)
    assert reported == [full]
    file.error = None
    save_each([changes.save], reported.append)
    save_each([changes.save], reported.append)
    assert reported == [full]
    assert file.writes == 1
