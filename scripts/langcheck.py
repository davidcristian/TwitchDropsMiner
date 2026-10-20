"""Fail when a language file in lang/ is not a JSON object or has a format field that English lacks."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from string import Formatter
from typing import Any

from sources import BOM, ROOT, UI_TEXT, Problem, read_text, repo_files


ENGLISH = "default_translation"
KeyPath = tuple[str, ...]
# A JSON string, with the colon after it when it is a key, or a bracket. Other values do not change the keys.
_JSON_TOKEN = re.compile(r'("(?:[^"\\]|\\.)*")(\s*:)?|[{}\[\]]')


def leaf_strings(data: dict[str, Any], path: KeyPath = ()) -> Iterator[tuple[KeyPath, str]]:
    """Yield each string in nested dicts with the keys that lead to it."""
    for key, value in data.items():
        if isinstance(value, dict):
            yield from leaf_strings(value, (*path, key))
        elif isinstance(value, str):
            yield (*path, key), value


def format_fields(template: str) -> set[str]:
    """Return the names of the str.format fields in a template, with those inside a format spec.

    Raises ValueError for a lone brace or an unknown conversion, as str.format does.
    """
    fields: set[str] = set()
    for _, name, spec, conversion in Formatter().parse(template):
        if conversion not in (None, "r", "s", "a"):
            raise ValueError(f"Unknown conversion specifier {conversion}")
        if name is not None:
            fields.add(name)
            fields |= format_fields(spec or "")
    return fields


def english_fields(source: str) -> dict[KeyPath, set[str]] | None:
    """Return the format fields of each string in the default_translation literal of a translate.py source.

    Returns None when the source has no such dict literal, and leaves out a string str.format cannot read.
    """
    try:
        module = ast.parse(source.removeprefix(BOM))
    except SyntaxError:
        return None
    for node in module.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id == ENGLISH and node.value is not None:
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            if not isinstance(value, dict):
                return None
            fields: dict[KeyPath, set[str]] = {}
            for path, text in leaf_strings(value):
                try:
                    fields[path] = format_fields(text)
                except ValueError:
                    pass
            return fields
    return None


def key_lines(text: str) -> dict[KeyPath, int]:
    """Return the line of each key in a valid JSON text, by the keys that lead to it."""
    lines: dict[KeyPath, int] = {}
    path: list[str] = []
    for token in _JSON_TOKEN.finditer(text):
        string, colon = token.groups()
        if string is None:
            if token.group() in "{[":
                path.append("")
            else:
                path.pop()
        elif colon:
            path[-1] = json.loads(string)
            lines[tuple(path)] = text.count("\n", 0, token.start()) + 1
    return lines


def field_problems(name: str, text: str, data: dict[str, Any], english: dict[KeyPath, set[str]]) -> list[Problem]:
    """Return a problem for each format field that English lacks, and each template str.format cannot read."""
    problems: list[Problem] = []
    lines = key_lines(text)
    for path, value in leaf_strings(data):
        if path not in english:
            continue
        key = ".".join(path)
        try:
            extra = sorted(format_fields(value) - english[path])
        except ValueError as error:
            # The code formats only the strings whose English has a field, so a lone brace elsewhere is text.
            if english[path]:
                problems.append(Problem(name, lines[path], f"{key} is not a str.format template: {error}"))
            continue
        problems.extend(
            Problem(name, lines[path], f"{key} has the field {{{field}}}, which the English string lacks")
            for field in extra
        )
    return problems


def lang_problems(name: str, text: str, english: dict[KeyPath, set[str]]) -> list[Problem]:
    """Return the problems with one language file, compared with the format fields of the English strings."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return [Problem(name, error.lineno, f"is not valid JSON: {error.msg}")]
    if not isinstance(data, dict):
        return [Problem(name, 1, "is not a JSON object")]
    return field_problems(name, text, data, english)


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of language files read and every problem in them."""
    source = read_text(root / UI_TEXT) if (root / UI_TEXT).is_file() else None
    english = english_fields(source) if source is not None else None
    problems: list[Problem] = []
    if english is None:
        problems.append(Problem(UI_TEXT, 1, f"has no {ENGLISH} dict literal to read the English strings from"))
    count = 0
    for name in repo_files(root):
        if not (name.startswith("lang/") and name.endswith(".json")):
            continue
        count += 1
        text = read_text(root / name)
        if text is None:
            problems.append(Problem(name, 1, "is not UTF-8 text"))
        else:
            problems.extend(lang_problems(name, text, english or {}))
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
