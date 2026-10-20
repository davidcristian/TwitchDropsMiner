import errno

import pytest

from savefiles import save_each


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
