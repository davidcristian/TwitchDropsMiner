"""List the repo's text files and read the prose in them: markdown, Python comments and docstrings."""
from __future__ import annotations

import ast
import inspect
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parent.parent
# Legal text and the translations into other languages, which the prose rules do not cover.
NOT_PROSE = ("LICENSE", "LICENSE.MIT", "lang/")
PYTHON_SUFFIXES = (".py", ".spec")
# The English text the app shows is written as string literals in this file.
UI_TEXT = "translate/english.py"
FENCES = ("```", "~~~")
_FENCE = re.compile(r"(`{3,}|~{3,})(.*)")
_QUOTE = re.compile(r"(?: {0,3}> ?)+")
# Python skips a byte order mark at the start of a file, but ast.parse and compile of a str reject it.
BOM = "\ufeff"
# The Unicode dashes that Latin text uses as punctuation, without the hyphens and the minus sign U+2212.
DASHES = {
    "\u2014": "an em dash",
    "\u2013": "an en dash",
    "\u2012": "a figure dash",
    "\u2015": "a horizontal bar",
    "\u2e3a": "a two-em dash",
    "\u2e3b": "a three-em dash",
    "\ufe31": "a vertical em dash",
    "\ufe32": "a vertical en dash",
    "\ufe58": "a small em dash",
}

Line = tuple[int, str]


class Problem(NamedTuple):
    """One rule broken at one line of one file."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


class Docstring(NamedTuple):
    """The number of the line a docstring's text starts on, and the text with the indentation removed."""

    line: int
    text: str


def write_utf8() -> None:
    """Make print write UTF-8, where Windows writes a pipe or a file in a code page that lacks most letters."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")


def repo_files(root: Path) -> list[str]:
    """Return the files git tracks or would track under root, relative to it, with forward slashes."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    names = {name for name in result.stdout.decode("utf-8").split("\0") if name}
    return sorted(name for name in names if (root / name).is_file())


def read_texts(root: Path, names: Iterable[str]) -> tuple[dict[str, str], list[Problem]]:
    """Return the text of each named file under root, and a problem for each that is not UTF-8 text.

    A file with a NUL byte is binary, such as an icon, and is left out of both.
    """
    texts: dict[str, str] = {}
    problems: list[Problem] = []
    for name in names:
        data = (root / name).read_bytes()
        if b"\0" in data:
            continue
        try:
            texts[name] = data.decode("utf-8")
        except UnicodeDecodeError as error:
            problems.append(Problem(name, data.count(b"\n", 0, error.start) + 1, "is not UTF-8 text"))
    return texts, problems


def read_text(path: Path) -> str | None:
    """Return the file's text, or None when it is binary or not UTF-8 text."""
    return read_texts(path.parent, [path.name])[0].get(path.name)


def is_prose_file(name: str) -> bool:
    """Whether the prose rules cover the file at this repo path."""
    return not name.startswith(NOT_PROSE)


def markdown_lines(text: str) -> list[Line]:
    """Return the numbered lines of a markdown text that are outside fenced code blocks."""
    lines: list[Line] = []
    fence = ""
    for number, line in enumerate(text.splitlines(), start=1):
        found = _FENCE.match(line.lstrip())
        marker, rest = found.groups() if found else ("", "")
        if fence:
            # CommonMark closes a fence only with the same character, repeated at least as many times,
            # and followed by nothing but spaces and tabs.
            if marker[:1] == fence[:1] and len(marker) >= len(fence) and not rest.strip(" \t"):
                fence = ""
        elif marker and not (marker[0] == "`" and "`" in rest):
            # CommonMark reads backticks followed by text that has a backtick as inline code, not as a fence.
            fence = marker
        else:
            lines.append((number, line))
    return lines


def comment_runs(source: str) -> list[list[Line]]:
    """Return the comments of a Python source, consecutive full-line comments grouped in one run."""
    runs: list[list[Line]] = []
    previous_full = -2
    # newline=None also ends a line at a lone CR, as ast.parse does, so that the line numbers agree.
    for token in tokenize.generate_tokens(io.StringIO(source, newline=None).readline):
        if token.type != tokenize.COMMENT:
            continue
        number = token.start[0]
        if number == 1 and token.string.startswith("#!"):
            continue
        text = token.string[1:].strip()
        full = token.line.strip().startswith("#")
        if full and runs and previous_full == number - 1:
            runs[-1].append((number, text))
        else:
            runs.append([(number, text)])
        previous_full = number if full else -2
    return runs


def docstrings(module: ast.Module) -> list[Docstring]:
    """Return the docstring of the module and of each class and function in it."""
    found: list[Docstring] = []
    for node in ast.walk(module):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            text = inspect.cleandoc(first.value.value)
            found.append(Docstring(first.lineno + _lines_before_text(first.value.value, text), text))
    return sorted(found)


def _lines_before_text(value: str, text: str) -> int:
    """Return how many blank lines inspect.cleandoc dropped from the start of value to give text."""
    # A "." before the first line stops cleandoc from dropping those lines, and changes no other line count.
    return inspect.cleandoc("." + value).count("\n") - text.count("\n")


def string_literals(module: ast.Module) -> list[Line]:
    """Return every string constant in a module that is not a docstring, with its line number."""
    skip = {id(node.value) for node in ast.walk(module) if isinstance(node, ast.Expr)}
    return sorted(
        (node.lineno, node.value)
        for node in ast.walk(module)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    )


def python_prose(name: str, source: str) -> list[list[Line]]:
    """Return the prose of a Python file as runs of lines: comments, docstrings, and UI text."""
    source = source.removeprefix(BOM)
    module = ast.parse(source)
    runs = comment_runs(source)
    for doc in docstrings(module):
        runs.append([(doc.line + index, text) for index, text in enumerate(doc.text.splitlines())])
    if name == UI_TEXT:
        runs.extend([line] for line in string_literals(module))
    return runs


def _unquoted(line: str) -> str:
    """Return a markdown line with the block quote markers at its start replaced by spaces."""
    found = _QUOTE.match(line)
    return " " * found.end() + line[found.end():] if found else line


def prose_runs(name: str, text: str) -> list[list[Line]]:
    """Return the prose of one repo file as runs of lines, read by the file's kind."""
    if name.endswith(".md"):
        return [[(number, _unquoted(line)) for number, line in markdown_lines(text)]]
    if name.endswith(PYTHON_SUFFIXES):
        try:
            return python_prose(name, text)
        except (SyntaxError, tokenize.TokenError):
            # syntaxcheck.py reports the error, and the other checks still read every line.
            pass
    return [list(enumerate(text.splitlines(), start=1))]
