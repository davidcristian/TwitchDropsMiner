"""Fail on a dash used as punctuation: an em dash, an en dash, or a spaced ASCII double hyphen in prose."""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from bannedwords import mask_run, runs
from sources import PYTHON_SUFFIXES, ROOT, Line, Problem, is_prose_file, prose_runs, read_text, repo_files


DASHES = {"\u2014": "an em dash", "\u2013": "an en dash"}
# A double hyphen with whitespace or a line break on both sides, so not a flag such as --root or part of ---.
SPACED = re.compile(r"(?<!\S)--(?!\S)")
# A line of only hyphens, pipes and colons is a horizontal rule, a heading underline or a table separator.
RULE = re.compile(r"[\s|:-]*")
# In code a double hyphen is an operator or the end of a command's options, so only these files are read for it.
PROSE_SUFFIXES = (".md", ".txt", *PYTHON_SUFFIXES)


def is_spaced(line: str, masked: str) -> bool:
    """Whether a line of prose has a spaced double hyphen that its masked text still has."""
    if RULE.fullmatch(line):
        return False
    return any(masked.startswith("--", found.start()) for found in SPACED.finditer(line))


def spaced_lines(run: Sequence[Line]) -> list[int]:
    """Return the number of each line of a prose run with a spaced double hyphen outside code spans, links and URLs."""
    return [number for (number, line), masked in zip(run, mask_run(run)) if is_spaced(line, masked)]


def dash_problems(name: str, text: str) -> list[Problem]:
    """Return a problem for each line of one file that uses a dash as punctuation."""
    problems = [
        Problem(name, number, f"{label}; restructure the sentence")
        for number, line in enumerate(text.splitlines(), start=1)
        for dash, label in DASHES.items()
        if dash in line
    ]
    if not name.endswith(PROSE_SUFFIXES):
        return problems
    problems.extend(
        Problem(name, number, "a spaced --; restructure the sentence")
        for lines in prose_runs(name, text)
        for run in runs(lines)
        for number in spaced_lines(run)
    )
    return problems


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of files read and every problem in them."""
    count = 0
    problems: list[Problem] = []
    for name in repo_files(root):
        text = read_text(root / name)
        if text is None or not is_prose_file(name):
            continue
        count += 1
        problems.extend(dash_problems(name, text))
    return count, sorted(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"dashcheck: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
