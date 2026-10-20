"""Fail when a Python file does not parse as Python 3.10, the version CI builds with."""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from sources import BOM, ROOT, PYTHON_SUFFIXES, Problem, read_text, repo_files


# ast.parse rejects most syntax newer than this, such as except*, but not the nested f-string quotes of 3.12
# or the starred forms of 3.11 that starred_problems finds. CI runs on Python 3.10, which rejects all of them.
TARGET = (3, 10)
STARRED = "does not parse as Python 3.10: a starred expression"


def _parenthesized(source: str, node: ast.Tuple) -> bool:
    """Return whether a tuple has its own parentheses, which Python 3.10 requires around a starred item."""
    last = node.elts[-1]
    if (node.end_lineno, node.end_col_offset) == (last.end_lineno, last.end_col_offset):
        return False
    return (ast.get_source_segment(source, node) or "").endswith(")")


def starred_problems(name: str, source: str, tree: ast.AST) -> list[Problem]:
    """Return each starred item in a subscript, as in a[*b], and each starred *args annotation."""
    problems: list[Problem] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Tuple) and node.slice.elts:
            if not _parenthesized(source, node.slice):
                starred = [item for item in node.slice.elts if isinstance(item, ast.Starred)]
                problems.extend(Problem(name, item.lineno, f"{STARRED} in a subscript") for item in starred)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.args.vararg is not None:
            annotation = node.args.vararg.annotation
            if isinstance(annotation, ast.Starred):
                problems.append(Problem(name, annotation.lineno, f"{STARRED} as the annotation of *args"))
    return sorted(problems)


def syntax_problems(name: str, source: str) -> list[Problem]:
    """Return the syntax errors that Python 3.10 finds in one Python source."""
    source = source.removeprefix(BOM)
    try:
        tree = ast.parse(source, filename=name, feature_version=TARGET)
        compile(source, name, "exec", dont_inherit=True)
    except SyntaxError as error:
        return [Problem(name, error.lineno or 1, f"does not parse as Python 3.10: {error.msg}")]
    return starred_problems(name, source, tree)


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
