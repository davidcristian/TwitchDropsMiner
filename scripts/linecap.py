"""Fail on a Python or markdown file over 300 lines, except the modules named here."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sources import ROOT, Problem, read_texts, repo_files


LIMITS = {".py": 300, ".md": 300}
# Inherited modules over the limit until the splits that the module-split task records are made.
# An entry fails once its module is under the limit, so the list only shrinks.
EXCEPTIONS = frozenset({
    "gui.py",
    "twitch.py",
})


def limit_for(name: str) -> int | None:
    """Return the line limit for the file at this repo path, or None when it has none."""
    for suffix, limit in LIMITS.items():
        if name.endswith(suffix):
            return limit
    return None


def cap_problems(lengths: dict[str, int]) -> list[Problem]:
    """Return the files over their limit, and the exceptions that are no longer needed."""
    problems: list[Problem] = []
    for name, length in sorted(lengths.items()):
        limit = limit_for(name)
        if limit is None or name in EXCEPTIONS:
            continue
        if length > limit:
            problems.append(Problem(name, length, f"{length} lines; the limit is {limit}, so split it"))
    for name in sorted(EXCEPTIONS):
        length = lengths.get(name)
        if length is None or length <= LIMITS[".py"]:
            problems.append(Problem(name, 1, "listed in EXCEPTIONS in linecap.py but not over the limit"))
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
    sys.exit(main())
