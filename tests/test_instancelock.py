from __future__ import annotations

import errno
import subprocess
import sys
from pathlib import Path

import pytest

from instancelock import lock_file

ROOT = Path(__file__).resolve().parent.parent
# A second process takes the lock and prints one line, then holds the lock until its input closes
HOLDER = """
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from instancelock import lock_file
lock = lock_file(Path(sys.argv[2]))
print(lock.file is not None, flush=True)
sys.stdin.read()
"""


@pytest.fixture
def holder():
    processes: list[subprocess.Popen[str]] = []

    def start(path: Path) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [sys.executable, "-c", HOLDER, str(ROOT), str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        processes.append(process)
        assert process.stdout is not None
        assert process.stdout.readline() == "True\n"
        return process

    yield start
    for process in processes:
        with process:
            process.kill()


def test_lock_file_takes_a_free_lock_and_keeps_the_file_open(tmp_path):
    path = tmp_path / "lock.file"
    lock = lock_file(path)
    assert lock.error is None
    assert lock.file is not None
    assert not lock.file.closed
    lock.file.close()
    assert path.read_text(encoding="utf8") == "ツ"


def test_lock_file_reports_a_lock_that_another_process_holds(tmp_path, holder):
    path = tmp_path / "lock.file"
    holder(path)
    assert lock_file(path) == (None, None)


def test_lock_file_takes_the_lock_after_the_process_that_held_it_ends(tmp_path, holder):
    path = tmp_path / "lock.file"
    process = holder(path)
    process.kill()
    process.wait()
    lock = lock_file(path)
    assert lock.error is None
    assert lock.file is not None
    lock.file.close()


def test_lock_file_returns_the_error_for_a_folder_it_cannot_write_to(tmp_path, unreadable):
    folder = tmp_path / "app"
    folder.mkdir()
    unreadable(folder)
    lock = lock_file(folder / "lock.file")
    assert lock.file is None
    assert isinstance(lock.error, PermissionError)


def test_lock_file_returns_the_error_for_a_path_that_is_a_folder(tmp_path):
    lock = lock_file(tmp_path)
    assert lock.file is None
    assert isinstance(lock.error, OSError)


@pytest.mark.skipif(sys.platform != "linux", reason="/dev/full, which fails every write, is a Linux device")
def test_lock_file_returns_the_error_of_a_write_to_a_full_disk():
    lock = lock_file(Path("/dev/full"))
    assert lock.file is None
    assert isinstance(lock.error, OSError)
    assert lock.error.errno == errno.ENOSPC


def test_lock_file_takes_no_lock_on_another_system(tmp_path, holder, monkeypatch):
    path = tmp_path / "lock.file"
    holder(path)
    monkeypatch.setattr(sys, "platform", "sunos5")
    lock = lock_file(path)
    assert lock.error is None
    assert lock.file is not None
    lock.file.close()
