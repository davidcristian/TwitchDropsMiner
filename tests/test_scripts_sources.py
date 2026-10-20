from __future__ import annotations

import ast
import os
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

import sources
from gitrepo import commit, make_repo, write
from sources import (
    BOM,
    Docstring,
    Problem,
    comment_runs,
    docstrings,
    is_prose_file,
    markdown_lines,
    prose_runs,
    python_prose,
    read_text,
    read_texts,
    repo_files,
    string_literals,
)


def test_problem_prints_as_path_line_and_message():
    assert str(Problem("docs/a.md", 4, "is broken")) == "docs/a.md:4: is broken"


def test_repo_files_lists_tracked_and_untracked_files_but_not_ignored_ones(tmp_path):
    root = make_repo(tmp_path, {".gitignore": "*.log\n", "a.py": "", "docs/deep/b.md": "", "run.log": ""})
    commit(root)
    (root / "c.txt").write_text("new\n")
    assert repo_files(root) == [".gitignore", "a.py", "c.txt", "docs/deep/b.md"]


def test_repo_files_skips_a_tracked_file_deleted_from_the_work_tree(tmp_path):
    root = make_repo(tmp_path, {"a.py": "", "b.py": ""})
    commit(root)
    (root / "b.py").unlink()
    assert repo_files(root) == ["a.py"]


def test_repo_files_returns_an_empty_list_for_an_empty_repo(tmp_path):
    assert repo_files(make_repo(tmp_path)) == []


def test_read_text_returns_the_text_of_a_utf8_file(tmp_path):
    path = tmp_path / "a.md"
    path.write_bytes("caf\u00e9\n".encode("utf-8"))
    assert read_text(path) == "caf\u00e9\n"


def test_read_text_returns_none_for_a_file_with_a_nul_byte(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"PNG\0\0data")
    assert read_text(path) is None


def test_read_text_returns_none_for_bytes_that_are_not_utf8(tmp_path):
    path = tmp_path / "latin1.txt"
    path.write_bytes("caf\u00e9".encode("latin-1"))
    assert read_text(path) is None


def test_read_texts_returns_the_text_of_each_utf8_file_and_leaves_out_a_file_with_a_nul_byte(tmp_path):
    write(tmp_path, {"a.md": "caf\u00e9\n", "docs/b.txt": "", "icon.ico": b"\0\0\x01\0\xff"})
    assert read_texts(tmp_path, ["a.md", "docs/b.txt", "icon.ico"]) == ({"a.md": "caf\u00e9\n", "docs/b.txt": ""}, [])


def test_read_texts_reports_a_file_that_is_not_utf8_at_the_line_of_its_first_bad_byte(tmp_path):
    write(tmp_path, {"notes.md": "one\ntwo \u2014\nthree \u00e9\n".encode("cp1252")})
    assert read_texts(tmp_path, ["notes.md"]) == ({}, [Problem("notes.md", 2, "is not UTF-8 text")])


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LICENSE", False),
        ("LICENSE.MIT", False),
        ("lang/Polski.json", False),
        ("README.md", True),
        ("docs/lang/notes.md", True),
        ("language.py", True),
    ],
)
def test_is_prose_file_leaves_out_the_licenses_and_the_translations(name, expected):
    assert is_prose_file(name) is expected


def test_markdown_lines_leaves_out_a_backtick_fence_and_a_tilde_fence():
    text = "one\n```python\ncode\n```\ntwo\n~~~\nmore code\n~~~\nthree\n"
    assert markdown_lines(text) == [(1, "one"), (5, "two"), (9, "three")]


def test_markdown_lines_keeps_a_tilde_line_inside_a_backtick_fence_as_code():
    text = "one\n```\n~~~\ninside\n```\ntwo\n"
    assert markdown_lines(text) == [(1, "one"), (6, "two")]


def test_markdown_lines_treats_an_indented_fence_in_a_list_item_as_a_fence():
    text = "- item\n  ```\n  code\n  ```\nafter\n"
    assert markdown_lines(text) == [(1, "- item"), (5, "after")]


def test_markdown_lines_leaves_out_everything_after_a_fence_that_nothing_closes():
    assert markdown_lines("one\n```\ncode\nmore\n") == [(1, "one")]


def test_markdown_lines_keeps_a_shorter_fence_inside_a_longer_one_as_code():
    text = "one\n````\n```\ninside\n```\n````\nafter\n"
    assert markdown_lines(text) == [(1, "one"), (7, "after")]


@pytest.mark.parametrize(
    ("text", "after"),
    [
        ("one\n```\ncode\n`````\nafter\n", 5),
        ("one\n~~~~\n~~~\ncode\n~~~~~\nafter\n", 6),
        ("one\n~~~\n```\ncode\n~~~\nafter\n", 6),
    ],
    ids=["longer closing fence", "shorter tilde line", "backtick line in a tilde fence"],
)
def test_markdown_lines_closes_a_fence_only_with_the_same_character_at_least_as_long(text, after):
    assert markdown_lines(text) == [(1, "one"), (after, "after")]


def test_markdown_lines_keeps_a_fence_line_with_an_info_string_inside_a_fence_as_code():
    text = "one\n```\n```python\ncode\n```\nafter\n"
    assert markdown_lines(text) == [(1, "one"), (6, "after")]


def test_markdown_lines_closes_a_fence_with_spaces_and_tabs_after_it():
    assert markdown_lines("one\n```\ncode\n```  \t\nafter\n") == [(1, "one"), (5, "after")]


def test_markdown_lines_reads_backticks_with_a_backtick_after_them_as_prose():
    text = "one\n```foo``` is inline\nafter\n"
    assert markdown_lines(text) == [(1, "one"), (2, "```foo``` is inline"), (3, "after")]


def test_markdown_lines_opens_a_tilde_fence_whose_info_string_has_a_backtick():
    assert markdown_lines("one\n~~~ `x`\ncode\n~~~\nafter\n") == [(1, "one"), (5, "after")]


def test_comment_runs_groups_consecutive_full_line_comments():
    source = "# one\n#  two\n\n# three\nx = 1\n"
    assert comment_runs(source) == [[(1, "one"), (2, "two")], [(4, "three")]]


def test_comment_runs_keeps_an_inline_comment_apart_from_the_comments_around_it():
    source = "# above\nx = 1  # inline\n# below\n"
    assert comment_runs(source) == [[(1, "above")], [(2, "inline")], [(3, "below")]]


def test_comment_runs_skips_a_shebang_only_on_the_first_line():
    source = "#!/usr/bin/env python3\n#!not a shebang\n"
    assert comment_runs(source) == [[(2, "!not a shebang")]]


def test_comment_runs_does_not_read_a_hash_inside_a_string():
    assert comment_runs("x = '# not a comment'\n") == []


def test_docstrings_returns_the_docstring_of_the_module_and_each_class_and_function():
    source = (
        '"""Module."""\n'
        "class A:\n"
        '    """Class."""\n'
        "    def f(self):\n"
        '        """Method."""\n'
        "async def g():\n"
        '    """Coroutine."""\n'
        "def h():\n"
        "    return 1\n"
    )
    assert docstrings(ast.parse(source)) == [
        Docstring(1, "Module."),
        Docstring(3, "Class."),
        Docstring(5, "Method."),
        Docstring(7, "Coroutine."),
    ]


def test_docstrings_removes_the_indentation_of_a_multiline_docstring():
    source = 'def f():\n    """First.\n\n    Second.\n    """\n'
    assert docstrings(ast.parse(source)) == [Docstring(2, "First.\n\nSecond.")]


def test_docstrings_numbers_a_docstring_from_the_line_its_text_starts_on():
    source = 'def f():\n    """\n\n    First.\n    Second.\n    """\n'
    assert docstrings(ast.parse(source)) == [Docstring(4, "First.\nSecond.")]


def test_docstrings_does_not_take_an_f_string_or_a_later_string_as_a_docstring():
    source = 'def f():\n    f"""{1}"""\ndef g():\n    x = 1\n    "later"\n'
    assert docstrings(ast.parse(source)) == []


def test_string_literals_returns_each_string_but_not_the_docstrings():
    source = '"""Module."""\nX = "one"\ndef f():\n    """Doc."""\n    return f"two {X}"\n'
    assert string_literals(ast.parse(source)) == [(2, "one"), (5, "two ")]


def test_python_prose_returns_the_comments_and_docstrings_but_not_the_strings():
    source = '"""Doc."""\n# Comment.\nX = "text"\n'
    assert python_prose("module.py", source) == [[(2, "Comment.")], [(1, "Doc.")]]


def test_python_prose_reads_the_strings_of_translate_py_as_prose():
    source = '"""Doc."""\nX = {"key": "Shown text"}\n'
    assert python_prose("translate.py", source) == [[(1, "Doc.")], [(2, "Shown text")], [(2, "key")]]


def test_python_prose_numbers_each_line_of_a_docstring():
    source = 'def f():\n    """First.\n    Second.\n    """\n'
    assert python_prose("module.py", source) == [[(2, "First."), (3, "Second.")]]


def test_python_prose_numbers_a_docstring_that_starts_on_the_line_after_its_quotes():
    source = 'def f():\n    """\n    Text here.\n    """\n'
    assert python_prose("module.py", source) == [[(3, "Text here.")]]


def test_python_prose_numbers_a_line_of_spaces_that_cleandoc_keeps_as_text():
    source = 'def f():\n    """\n        \n    Text.\n    """\n'
    assert python_prose("module.py", source) == [[(3, "    "), (4, "Text.")]]


def test_bom_is_the_utf8_byte_order_mark():
    assert BOM.encode("utf-8") == b"\xef\xbb\xbf"


def test_python_prose_reads_a_file_with_a_bom_like_the_same_file_without_it():
    source = '"""Doc."""\n# Comment.\nX = "text"\n'
    assert python_prose("module.py", BOM + source) == python_prose("module.py", source)
    assert prose_runs("tool.py", BOM + source) == [[(2, "Comment.")], [(1, "Doc.")]]


def test_prose_runs_reads_markdown_outside_fences_as_one_run():
    assert prose_runs("a.md", "one\n```\ncode\n```\n\ntwo\n") == [[(1, "one"), (5, ""), (6, "two")]]


@pytest.mark.parametrize("name", ["tool.py", "build.spec"])
def test_prose_runs_reads_a_python_file_as_comments_and_docstrings(name):
    assert prose_runs(name, "x = 1  # Note.\n") == [[(1, "Note.")]]


def test_prose_runs_reads_every_line_of_another_text_file():
    assert prose_runs("notes.txt", "one\n\ntwo\n") == [[(1, "one"), (2, ""), (3, "two")]]


@pytest.mark.parametrize(
    ("name", "text"),
    [("broken.py", "x = (\n# one\n"), ("build.spec", "def f():\nreturn 1\n")],
    ids=["syntax error", "indentation error"],
)
def test_prose_runs_reads_every_line_of_a_python_file_that_does_not_parse(name, text):
    first, second = text.splitlines()
    assert prose_runs(name, text) == [[(1, first), (2, second)]]


def test_prose_runs_reads_every_line_of_a_python_file_that_does_not_tokenize(monkeypatch):
    def python_prose(name, source):
        raise tokenize.TokenError("EOF in multi-line statement", (2, 0))

    monkeypatch.setattr(sources, "python_prose", python_prose)
    assert prose_runs("tool.py", "x = 1\n# Note.\n") == [[(1, "x = 1"), (2, "# Note.")]]


# A new interpreter has loaded no module of scripts/ yet, so it shows what importing one script loads.
LOADED = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "__import__(sys.argv[2])\n"
    "print(*sorted(name for name, module in sys.modules.items()"
    " if str(getattr(module, '__file__', '')).startswith(sys.argv[1])))\n"
)


@pytest.mark.parametrize(
    ("script", "loaded"),
    [
        ("syntaxcheck", ["sources", "syntaxcheck"]),
        ("dashcheck", ["bannedwords", "dashcheck", "sources"]),
        ("prosecheck", ["bannedwords", "prosecheck", "sources"]),
    ],
)
def test_a_prose_check_script_loads_the_shared_helpers_and_no_other_check_script(script, loaded):
    folder = str(Path(sources.__file__).parent) + os.sep
    command = [sys.executable, "-I", "-c", LOADED, folder, script]
    assert subprocess.run(command, capture_output=True, text=True, check=True).stdout.split() == loaded
