"""Check the language files in lang/ against the English strings, and print how many strings each one lacks."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from string import Formatter
from typing import Any, NamedTuple

from sources import BOM, ROOT, UI_TEXT, Problem, read_text, repo_files


ENGLISH = "default_translation"
KeyPath = tuple[str, ...]
# A JSON string, with the colon after it when it is a key, or a bracket. Other values do not change the keys.
_JSON_TOKEN = re.compile(r'("(?:[^"\\]|\\.)*")(\s*:)?|[{}\[\]]')
JSON_TYPES = {
    dict: "an object", list: "a list", str: "a string", int: "a number", float: "a number", bool: "true or false",
    type(None): "null",
}


class Result(NamedTuple):
    """The number of language files read, the problems in them, and the English strings each file lacks."""

    files: int
    problems: list[Problem]
    missing: dict[str, int]


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


def english_strings(source: str) -> dict[str, Any] | None:
    """Return the default_translation dict literal of a translate/english.py source, or None when it has none."""
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
            return value if isinstance(value, dict) else None
    return None


def english_fields(english: dict[str, Any]) -> dict[KeyPath, set[str]]:
    """Return the format fields of each English string, leaving out a string str.format cannot read."""
    fields: dict[KeyPath, set[str]] = {}
    for path, text in leaf_strings(english):
        try:
            fields[path] = format_fields(text)
        except ValueError:
            pass
    return fields


def unread_keys(data: dict[str, Any], english: dict[str, Any], path: KeyPath = ()) -> Iterator[tuple[KeyPath, str]]:
    """Yield each key that `merge_json` in utils/jsonfile.py removes or replaces when the app loads data, and why."""
    for key, value in data.items():
        key_path = (*path, key)
        if key not in english:
            yield key_path, "is a key that the app does not read"
        elif type(value) is not type(english[key]):
            found, expected = JSON_TYPES[type(value)], JSON_TYPES[type(english[key])]
            yield key_path, f"is {found} where English has {expected}, so the app does not read it"
        elif isinstance(value, dict):
            yield from unread_keys(value, english[key], key_path)


def missing_strings(data: dict[str, Any], english: dict[str, Any]) -> int:
    """Return the number of English strings that data lacks, which the app shows in English."""
    count = 0
    for path, _ in leaf_strings(english):
        value: Any = data
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if not isinstance(value, str):
            count += 1
    return count


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


def parse_language(name: str, text: str) -> dict[str, Any] | Problem:
    """Return the data of a language file, or the problem that keeps the app from reading it."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return Problem(name, error.lineno, f"is not valid JSON: {error.msg}")
    if not isinstance(data, dict):
        return Problem(name, 1, "is not a JSON object")
    return data


def lang_problems(name: str, text: str, english: dict[str, Any] | None) -> list[Problem]:
    """Return the problems with one language file, compared with the English strings when they are known."""
    data = parse_language(name, text)
    if isinstance(data, Problem):
        return [data]
    if english is None:
        return []
    lines = key_lines(text)
    problems = [Problem(name, lines[path], f"{'.'.join(path)} {reason}") for path, reason in unread_keys(data, english)]
    problems += field_problems(name, text, data, english_fields(english))
    return sorted(problems, key=lambda problem: problem.line)


def check(root: Path) -> Result:
    """Return the number of language files read, every problem in them, and the strings each one lacks."""
    source = read_text(root / UI_TEXT) if (root / UI_TEXT).is_file() else None
    english = english_strings(source) if source is not None else None
    problems: list[Problem] = []
    missing: dict[str, int] = {}
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
            continue
        problems.extend(lang_problems(name, text, english))
        data = parse_language(name, text)
        if english is not None and not isinstance(data, Problem):
            missing[name] = missing_strings(data, english)
    return Result(count, problems, missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = check(args.root)
    for problem in result.problems:
        print(problem)
    # a string that a language lacks shows in English, which AGENTS.md allows for a new string
    for name, count in result.missing.items():
        print(f"langcheck: {name} lacks {count} strings, which show in English")
    print(f"langcheck: {result.files} files, {len(result.problems)} problems")
    return 1 if result.problems else 0


if __name__ == "__main__":
    sys.exit(main())
