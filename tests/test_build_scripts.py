from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# On Windows, `bash` can start WSL, which would run the script in another system
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="the shell scripts run in bash on Linux and macOS"
)


def run_script(folder: Path, name: str, *args: str, tools: dict[str, int]) -> subprocess.CompletedProcess[str]:
    """Run a copy of the script in folder, with each tool in env/bin replaced by a stub that exits with its status."""
    shutil.copy(REPO / name, folder / name)
    bin_dir = folder / "env" / "bin"
    bin_dir.mkdir(parents=True)
    for tool, status in tools.items():
        stub = bin_dir / tool
        stub.write_text(f"#!/bin/sh\nexit {status}\n")
        stub.chmod(0o755)
    # no input, as when another script runs it: the prompt's `read` then fails
    return subprocess.run(
        ["bash", str(folder / name), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=folder
    )


@pytest.mark.parametrize("args", [("--nopause",), ()])
def test_a_successful_build_exits_with_status_0(tmp_path, args):
    result = run_script(tmp_path, "build.sh", *args, tools={"pyinstaller": 0})

    assert "Build completed successfully." in result.stdout
    assert result.returncode == 0


def test_a_failed_build_exits_with_status_1(tmp_path):
    result = run_script(tmp_path, "build.sh", "--nopause", tools={"pyinstaller": 1})

    assert "PyInstaller build failed." in result.stdout
    assert result.returncode == 1


def test_a_successful_setup_exits_with_status_0(tmp_path):
    result = run_script(tmp_path, "setup_env.sh", tools={"python": 0, "pip": 0})

    assert "Environment setup completed successfully." in result.stdout
    assert result.returncode == 0
