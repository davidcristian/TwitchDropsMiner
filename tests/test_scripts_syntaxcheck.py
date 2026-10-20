from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import syntaxcheck
from gitrepo import make_repo
from sources import Problem

SCRIPT = Path(syntaxcheck.__file__)


def test_syntax_problems_returns_nothing_for_python_310_code():
    source = "match x:\n    case [a, *rest]:\n        y = (z := a)\n"
    assert syntaxcheck.syntax_problems("ok.py", source) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        ("x = 1\ntry: pass\nexcept* ValueError: pass\n", 3),
        ("x = 1\ndef first[T](items: list[T]) -> T:\n    return items[0]\n", 2),
        pytest.param(
            "x = {}\n\ny = f\"{x[\"k\"]}\"\n",
            3,
            # ast.parse of Python 3.12 accepts these quotes even with feature_version, as syntaxcheck.py says
            marks=pytest.mark.skipif(sys.version_info >= (3, 12), reason="found only by Python 3.10 and 3.11"),
        ),
        ("x = 1\ny = a[\n    1, *b]\n", 3),
        ("x = 1\n\nasync def f(*args: *Ts): pass\n", 3),
    ],
    ids=[
        "except star of 3.11",
        "type parameters of 3.12",
        "nested f-string quotes of 3.12",
        "starred subscript of 3.11",
        "starred args annotation of 3.11",
    ],
)
def test_syntax_problems_reports_syntax_newer_than_python_310_at_its_line(source, line):
    [problem] = syntaxcheck.syntax_problems("new.py", source)
    assert (problem.path, problem.line) == ("new.py", line)
    assert problem.message.startswith("does not parse as Python 3.10: ")


@pytest.mark.parametrize(
    "source",
    [
        "x = a[(*b,)]\n",
        "x = a[c, (*b,)]\n",
        "x = a[(c, *(b))]\n",
        "x = a[\n    (c,\n     *b  # )\n    )\n]\n",
        "x = a[f(*b), [*c]]\n",
        "x = a[()]\n",
        "def f(*args: int, **kwargs: str): pass\n",
        "f = lambda *args: args\n",
    ],
)
def test_syntax_problems_accepts_the_starred_forms_of_python_310(source):
    assert syntaxcheck.syntax_problems("ok.py", source) == []


@pytest.mark.skipif(sys.version_info < (3, 11), reason="ast.parse of Python 3.10 rejects these forms first")
def test_syntax_problems_reports_each_starred_form_of_python_311_in_line_order():
    source = "def f(*args: *Ts):\n    return a[*b,]\n\n\nx = a[(c), *(d)]\ny = a[*e,\n      *f]\n"
    assert syntaxcheck.syntax_problems("new.py", source) == [
        Problem("new.py", 1, "does not parse as Python 3.10: a starred expression as the annotation of *args"),
        Problem("new.py", 2, "does not parse as Python 3.10: a starred expression in a subscript"),
        Problem("new.py", 5, "does not parse as Python 3.10: a starred expression in a subscript"),
        Problem("new.py", 6, "does not parse as Python 3.10: a starred expression in a subscript"),
        Problem("new.py", 7, "does not parse as Python 3.10: a starred expression in a subscript"),
    ]


def test_syntax_problems_reports_an_error_that_only_the_compiler_finds():
    [problem] = syntaxcheck.syntax_problems("bad.py", "x = 1\nreturn x\n")
    assert problem == Problem("bad.py", 2, "does not parse as Python 3.10: 'return' outside function")


def test_syntax_problems_accepts_a_file_that_starts_with_a_utf8_bom():
    assert syntaxcheck.syntax_problems("bom.py", "\ufeffx = 1\n") == []


def test_syntax_problems_reports_an_error_after_a_bom_at_its_line():
    [problem] = syntaxcheck.syntax_problems("bom.py", "\ufeffx = 1\ny = (\n")
    assert (problem.path, problem.line) == ("bom.py", 2)


def test_syntax_problems_reports_a_bom_that_is_not_at_the_start():
    [problem] = syntaxcheck.syntax_problems("bom.py", "x = 1\n\ufeffy = 2\n")
    assert (problem.path, problem.line) == ("bom.py", 2)
    assert "U+FEFF" in problem.message


def test_check_accepts_a_file_saved_with_a_utf8_bom(tmp_path):
    root = make_repo(tmp_path, {"bom.py": b"\xef\xbb\xbfx = 1\n"})
    assert syntaxcheck.check(root) == (1, [])


def test_check_reads_py_and_spec_files_and_nothing_else(tmp_path):
    root = make_repo(tmp_path, {
        "a.py": "x = 1\n",
        "pkg/b.py": "def f(:\n",
        "build.spec": "a = Analysis(\n",
        "notes.txt": "def f(:\n",
    })
    count, problems = syntaxcheck.check(root)
    assert count == 3
    assert [(problem.path, problem.line) for problem in problems] == [("build.spec", 1), ("pkg/b.py", 1)]


def test_check_reports_a_python_file_that_is_not_utf8_and_does_not_count_it(tmp_path):
    root = make_repo(tmp_path, {"a.py": "x = 1\n", "latin.py": "s = 'caf\u00e9'\n".encode("latin-1")})
    assert syntaxcheck.check(root) == (1, [Problem("latin.py", 1, "is not UTF-8 text")])


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {"bad.py": "x = (\n"})
    assert syntaxcheck.main(["--root", str(root)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("bad.py:1: does not parse as Python 3.10: ")
    assert lines[1] == "syntaxcheck: 1 files, 1 problems"


def test_main_returns_0_when_every_file_parses(tmp_path, capsys):
    root = make_repo(tmp_path, {"a.py": "x = 1\n"})
    assert syntaxcheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "syntaxcheck: 1 files, 0 problems\n"


def test_the_script_run_as_a_program_exits_with_the_status_of_main(tmp_path):
    root = make_repo(tmp_path, {"bad.py": "x = (\n"})
    result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout.endswith("syntaxcheck: 1 files, 1 problems\n")
