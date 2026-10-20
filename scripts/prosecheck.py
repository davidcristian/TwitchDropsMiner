"""Fail on a banned word in prose, and on a comment block or docstring over three lines."""
from __future__ import annotations

import argparse
import ast
import sys
import tokenize
from pathlib import Path

import bannedwords
from sources import (
    BOM, PYTHON_SUFFIXES, ROOT, Line, Problem, comment_runs, docstrings, is_prose_file, prose_runs, read_texts,
    repo_files,
)


MAX_BLOCK_LINES = 3
RULES = "AGENTS.md"


def word_problems(name: str, text: str, table: bannedwords.Table) -> list[Problem]:
    """Return a problem for each banned word in the prose of one file."""
    pattern = bannedwords.compile_words(table.words)
    problems: list[Problem] = []
    for lines in prose_runs(name, text):
        if name == RULES:
            lines = [(number, line) for number, line in lines if not table.first <= number <= table.last]
        for run in bannedwords.runs(lines):
            problems.extend(
                Problem(name, hit.line, f'banned word "{hit.word}"; the table in AGENTS.md gives a replacement')
                for hit in bannedwords.find_words(run, pattern)
            )
    return problems


def block_problems(name: str, source: str) -> list[Problem]:
    """Return a problem for each comment block or docstring of a Python file over three lines."""
    source = source.removeprefix(BOM)
    try:
        module = ast.parse(source)
        long_runs: list[list[Line]] = [run for run in comment_runs(source) if len(run) > MAX_BLOCK_LINES]
    except (SyntaxError, tokenize.TokenError):
        # syntaxcheck.py reports a file that does not parse. tokenize rejects some files that do parse,
        # such as one that ends in a backslash and a CRLF in Python 3.10, and this check skips those.
        return []
    problems = [
        Problem(name, run[0][0], f"comment block of {len(run)} lines; the limit is {MAX_BLOCK_LINES}")
        for run in long_runs
    ]
    problems.extend(
        Problem(name, doc.line, f"docstring of {len(doc.text.splitlines())} lines; the limit is {MAX_BLOCK_LINES}")
        for doc in docstrings(module)
        if len(doc.text.splitlines()) > MAX_BLOCK_LINES
    )
    return problems


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of files read and every problem in them."""
    table = bannedwords.parse_table((root / RULES).read_text(encoding="utf-8"))
    texts, problems = read_texts(root, [name for name in repo_files(root) if is_prose_file(name)])
    for name, text in texts.items():
        problems.extend(word_problems(name, text, table))
        if name.endswith(PYTHON_SUFFIXES):
            problems.extend(block_problems(name, text))
    return len(texts), sorted(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"prosecheck: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
