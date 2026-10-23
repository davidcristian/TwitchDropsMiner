"""Fail on a Python or markdown file over 300 lines."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sources import ROOT, Problem, read_texts, repo_files, write_utf8


LIMITS = {".py": 300, ".md": 300}


def limit_for(name: str) -> int | None:
    """Return the line limit for the file at this repo path, or None when it has none."""
    for suffix, limit in LIMITS.items():
        if name.endswith(suffix):
            return limit
    return None


def cap_problems(lengths: dict[str, int]) -> list[Problem]:
    """Return the files over their limit."""
    problems: list[Problem] = []
    for name, length in sorted(lengths.items()):
        limit = limit_for(name)
        if limit is None:
            continue
        if length > limit:
            problems.append(Problem(name, length, f"{length} lines; the limit is {limit}, so split it"))
    return problems


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of files measured and every problem in them."""
    texts, problems = read_texts(root, [name for name in repo_files(root) if limit_for(name) is not None])
    lengths = {name: len(text.splitlines()) for name, text in texts.items()}
    return len(lengths), problems + cap_problems(lengths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"linecap: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    write_utf8()
    sys.exit(main())
