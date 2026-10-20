from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent / "main.py"
# Runs main.py as a script on a fake Python 3.9, which cannot install truststore and has no typing.ParamSpec
# for utils.py to import
OLD_PYTHON = """
import runpy
import sys
sys.version_info = (3, 9, 18, "final", 0)
sys.modules["truststore"] = None
sys.modules["utils"] = None
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def test_an_older_python_stops_with_the_version_message(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", OLD_PYTHON, str(MAIN)], capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 1
    assert result.stderr.splitlines()[-1] == "RuntimeError: Python 3.10 or higher is required"
