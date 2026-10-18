"""Build small git repos with real files in them, for the tests of the scripts in scripts/."""
from __future__ import annotations

import subprocess
from pathlib import Path

# A commit needs an author, and the user's own signing setting and hooks must not run in a test repo.
_GIT = [
    "git",
    "-c", "user.name=t",
    "-c", "user.email=t@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "core.hooksPath=/dev/null",
]

# Banned words for the test tables, joined from parts so that the prose scans pass on this file.
SEAM = "se" + "am"
BEARING = "load-" + "bear" + "ing"
HOOD = "under the " + "ho" + "od"
HANGING = "low-" + "hang" + "ing"
TABLE = (
    "| Do not write | Write instead |\n"
    "| --- | --- |\n"
    f"| {SEAM}, {SEAM}s | boundary |\n"
    f"| {BEARING} | required |\n"
    f"| {HOOD}, {HANGING} | say it literally |\n"
)
AGENTS = f"# Rules\n\nThe table of words.\n\n{TABLE}\nThe end.\n"


def git(root: Path, *args: str) -> str:
    """Run git in root and return what it prints."""
    result = subprocess.run([*_GIT, "-C", str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout


def write(root: Path, files: dict[str, str | bytes]) -> None:
    """Write each file under root, with its folders. A str is written as UTF-8, bytes as they are."""
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_bytes(content.encode("utf-8"))


def make_repo(root: Path, files: dict[str, str | bytes] | None = None) -> Path:
    """Create a git repo at root that holds the files, none of them added, and return root."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    write(root, files or {})
    return root


def commit(root: Path, message: str = "chore: add the files") -> str:
    """Add every file in the repo, commit them, and return the hash of the commit."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()
