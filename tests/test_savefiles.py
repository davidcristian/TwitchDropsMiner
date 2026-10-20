import errno

import pytest

from savefiles import UnsavedChanges, save_each


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
