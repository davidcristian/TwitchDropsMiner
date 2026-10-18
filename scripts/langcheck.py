"""Fail when a language file in lang/ is not a JSON object."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sources import ROOT, Problem, read_text, repo_files


def lang_problems(name: str, text: str) -> list[Problem]:
    """Return the problem with one language file, if it has one."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return [Problem(name, error.lineno, f"is not valid JSON: {error.msg}")]
    if not isinstance(data, dict):
        return [Problem(name, 1, "is not a JSON object")]
    return []


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of language files read and every problem in them."""
    count = 0
    problems: list[Problem] = []
    for name in repo_files(root):
        if not (name.startswith("lang/") and name.endswith(".json")):
            continue
        count += 1
        text = read_text(root / name)
        if text is None:
            problems.append(Problem(name, 1, "is not UTF-8 text"))
        else:
            problems.extend(lang_problems(name, text))
    return count, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"langcheck: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
