from __future__ import annotations

import shlex
import subprocess
import sys

import pytest

import commitlint
from bannedwords import parse_table
from gitrepo import AGENTS, SEAM, git, make_repo

TABLE = parse_table(AGENTS)
COMMENTED = f"fix: a\n\nBody.\n#12 is the {SEAM} it fixes.\n"
FIXES_12 = "cites an issue or pull request number ('#12'); name the behavior instead"


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo", {"AGENTS.md": AGENTS})


def test_check_reads_a_comment_line_of_a_message_that_no_editor_opened(repo):
    assert commitlint.check(COMMENTED, TABLE, repo, edited=False) == [
        f"line 4 {FIXES_12}",
        f'line 4 uses the banned word "{SEAM}"; the table in AGENTS.md gives a replacement',
    ]


def test_check_skips_a_comment_line_of_an_edited_message(repo):
    assert commitlint.check(COMMENTED, TABLE, repo, edited=True) == []


def test_check_reads_the_lines_below_the_scissors_line_only_when_no_editor_opened(repo):
    text = f"fix: a\n\nBody.\n{commitlint.SCISSORS}\nIt fixes #12.\n"
    assert commitlint.check(text, TABLE, repo, edited=False) == [f"line 5 {FIXES_12}"]
    assert commitlint.check(text, TABLE, repo, edited=True) == []


@pytest.mark.parametrize(("editor", "status"), [(None, 0), ("true", 0), ("vi", 0), (":", 1)])
def test_main_reads_the_comment_lines_only_when_git_editor_is_a_colon(repo, tmp_path, monkeypatch, editor, status):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: a\n\n#12 is fixed.\n", encoding="utf-8")
    if editor is not None:
        monkeypatch.setenv("GIT_EDITOR", editor)
    assert commitlint.main([str(message), "--root", str(repo)]) == status


@pytest.fixture
def hooked(repo, tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "commit-msg"
    command = shlex.join([sys.executable, commitlint.__file__, "--root", str(repo)])
    hook.write_text(f'#!/bin/sh\nexec {command} "$1"\n', encoding="utf-8")
    hook.chmod(0o755)
    return repo, f"core.hooksPath={hooks}"


@pytest.mark.skipif(sys.platform == "win32", reason="the hook is a shell script")
def test_a_commit_without_an_editor_fails_on_a_reference_in_a_comment_line(hooked):
    repo, hooks = hooked
    with pytest.raises(subprocess.CalledProcessError) as error:
        git(repo, "-c", hooks, "commit", "-q", "--allow-empty", "-m", "fix: a", "-m", "#12 is fixed.")
    assert error.value.stderr == f"commitlint: line 3 {FIXES_12}\n"


@pytest.mark.skipif(sys.platform == "win32", reason="the hook is a shell script")
def test_a_commit_from_an_editor_passes_and_loses_the_comment_line(hooked, tmp_path, monkeypatch):
    repo, hooks = hooked
    editor = tmp_path / "editor.py"
    editor.write_text(
        "import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('fix: a\\n\\nBody.\\n#12 is fixed.\\n')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_EDITOR", shlex.join([sys.executable, str(editor)]))
    git(repo, "-c", hooks, "commit", "-q", "--allow-empty")
    assert git(repo, "log", "-1", "--format=%B") == "fix: a\n\nBody.\n\n"
