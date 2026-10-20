from __future__ import annotations

from types import SimpleNamespace

import pytest

from commitlint import is_commit
from gitrepo import commit, git, isolate_git, make_repo, write
from sources import repo_files


@pytest.fixture(scope="module")
def hook_variables(tmp_path_factory):
    # A module fixture runs before the autouse fixture in conftest.py, as a git hook sets its variables before
    # pytest starts. So this fixture isolates git itself while it builds its repos.
    with pytest.MonkeyPatch.context() as patch:
        isolate_git(patch, tmp_path_factory.mktemp("home"))
        outer = make_repo(tmp_path_factory.mktemp("outer"), {"a.txt": "outer\n"})
        ready = make_repo(tmp_path_factory.mktemp("ready"), {"b.txt": "ready\n"})
        repos = SimpleNamespace(
            outer=outer,
            outer_head=commit(outer),
            outer_config=(outer / ".git" / "config").read_bytes(),
            ready=ready,
            ready_head=commit(ready),
        )
        patch.setenv("GIT_DIR", str(outer / ".git"))
        patch.setenv("GIT_INDEX_FILE", str(outer / ".git" / "index"))
        yield repos


@pytest.fixture(scope="module")
def user_git_files(tmp_path_factory):
    # The machine's own git setup, set before the autouse fixture runs: a global config that names one ignore
    # file, and the default ignore file under XDG_CONFIG_HOME, which git reads when no config names one.
    with pytest.MonkeyPatch.context() as patch:
        home = tmp_path_factory.mktemp("user")
        config = f"[core]\n\texcludesFile = {(home / 'python.ignore').as_posix()}\n"
        write(home, {".gitconfig": config, "python.ignore": "*.py\n", "config/git/ignore": "*.md\n"})
        patch.setenv("HOME", str(home))
        patch.setenv("XDG_CONFIG_HOME", str(home / "config"))
        yield


def test_make_repo_and_commit_change_only_the_test_repo_when_git_variables_name_another(hook_variables, tmp_path):
    root = make_repo(tmp_path / "inner", {"c.txt": "inner\n"})
    head = commit(root)
    outer = hook_variables.outer
    assert git(outer, "log", "--all", "--format=%H") == f"{hook_variables.outer_head}\n"
    assert git(outer, "ls-files") == "a.txt\n"
    assert (outer / ".git" / "config").read_bytes() == hook_variables.outer_config
    assert (root / ".git").is_dir()
    assert git(root, "log", "--all", "--format=%H") == f"{head}\n"
    assert git(root, "ls-files") == "c.txt\n"


def test_is_commit_reads_the_test_repo_when_git_variables_name_another(hook_variables):
    assert is_commit(hook_variables.ready_head, hook_variables.ready) is True
    assert is_commit(hook_variables.outer_head, hook_variables.ready) is False


def test_repo_files_lists_the_files_that_the_users_own_ignore_files_name(user_git_files, tmp_path):
    root = make_repo(tmp_path, {"a.md": "", "b.py": "", "c.txt": ""})
    assert repo_files(root) == ["a.md", "b.py", "c.txt"]
