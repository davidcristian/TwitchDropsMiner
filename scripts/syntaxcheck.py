"""Fail when a Python file does not parse as Python 3.10, the version CI builds with."""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from sources import BOM, ROOT, PYTHON_SUFFIXES, Problem, read_text, repo_files


# ast.parse rejects most syntax newer than this, such as except*, but not the nested f-string quotes of 3.12.
# CI runs on Python 3.10, which rejects those as well.
TARGET = (3, 10)


def syntax_problems(name: str, source: str) -> list[Problem]:
    """Return the syntax error in one Python source, if it has one."""
    source = source.removeprefix(BOM)
    try:
        ast.parse(source, filename=name, feature_version=TARGET)
        compile(source, name, "exec", dont_inherit=True)
    except SyntaxError as error:
        return [Problem(name, error.lineno or 1, f"does not parse as Python 3.10: {error.msg}")]
    return []


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of Python files read and every problem in them."""
    count = 0
    problems: list[Problem] = []
    for name in repo_files(root):
        if not name.endswith(PYTHON_SUFFIXES):
            continue
        source = read_text(root / name)
        if source is None:
            problems.append(Problem(name, 1, "is not UTF-8 text"))
            continue
        count += 1
        problems.extend(syntax_problems(name, source))
    return count, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"syntaxcheck: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
