"""Read the banned-word table in AGENTS.md and find those words in prose."""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import NamedTuple

from sources import Line


HEADER = "Do not write"
_SEPARATOR = re.compile(r":?-+:?")
# A code span may cross one line break, and a span that closes on its own line is taken first.
_CODE_SPAN = re.compile(r"(`+)(?!`)(?:[^\n]*\n)??[^\n]*?(?<!`)\1(?!`)")
_LINK_TARGET = re.compile(r"(?<=\])\([^)\n]*\)")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)


class TableError(Exception):
    """The banned-word table is missing or lists no word."""


class Table(NamedTuple):
    """The banned words, and the line numbers of the table's first and last row."""

    words: tuple[str, ...]
    first: int
    last: int


class Hit(NamedTuple):
    """One banned word found on one line."""

    line: int
    word: str


def _cells(line: str) -> list[str]:
    text = line.strip()
    if not text.startswith("|"):
        return []
    return [cell.strip() for cell in text.strip("|").split("|")]


def parse_table(text: str) -> Table:
    """Return the words of the table whose first column is headed HEADER."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _cells(line)[:1] != [HEADER]:
            continue
        rows: list[list[str]] = []
        for row in lines[index + 1:]:
            cells = _cells(row)
            if not cells:
                break
            rows.append(cells)
        words = tuple(
            word.strip().lower()
            for cells in rows
            if not all(_SEPARATOR.fullmatch(cell) for cell in cells)
            for word in cells[0].split(",")
            if word.strip()
        )
        if not words:
            raise TableError("the banned-word table lists no word")
        return Table(words, first=index + 1, last=index + len(rows) + 1)
    raise TableError(f"no table has a first column headed {HEADER!r}")


def compile_words(words: Iterable[str]) -> re.Pattern[str]:
    """Return one pattern that matches any of the words as a whole word, in any case.

    The words of a phrase may be separated by any whitespace, including a line break.
    """
    phrases = {r"\s+".join(map(re.escape, word.split())) for word in words}
    longest_first = sorted(phrases, key=lambda phrase: (-len(phrase), phrase))
    return re.compile(rf"(?<![\w-])(?:{'|'.join(longest_first)})(?![\w-])", re.IGNORECASE)


def mask(text: str) -> str:
    """Blank out code spans, link targets and URLs, which the prose rules do not cover, keeping line breaks."""
    for pattern in (_CODE_SPAN, _LINK_TARGET, _URL):
        text = pattern.sub(lambda found: _blank(found.group()), text)
    return text


def _blank(text: str) -> str:
    """Return the text with a space in place of every character except a line break."""
    return "\n".join(" " * len(part) for part in text.split("\n"))


def runs(lines: Iterable[Line]) -> list[list[Line]]:
    """Split numbered lines into runs of consecutive lines that are not blank."""
    grouped: list[list[Line]] = []
    for number, text in lines:
        if not text.strip():
            continue
        if grouped and grouped[-1][-1][0] == number - 1:
            grouped[-1].append((number, text))
        else:
            grouped.append([(number, text)])
    return grouped


def mask_run(run: Sequence[Line]) -> list[str]:
    """Return the text of each line of a run, masked as one text so that a code span may cross a line break."""
    joined = mask("\n".join(text for _, text in run))
    masked: list[str] = []
    start = 0
    # A string of translate.py is one line that can hold line breaks, so the lines are cut by length.
    for _, text in run:
        masked.append(joined[start:start + len(text)])
        start += len(text) + 1
    return masked


def find_words(run: Sequence[Line], pattern: re.Pattern[str]) -> list[Hit]:
    """Return every banned word in a run of consecutive lines, on the line where it starts."""
    masked = mask_run(run)
    hits: list[Hit] = []
    for index, (number, _) in enumerate(run):
        here = masked[index]
        following = masked[index + 1] if index + 1 < len(masked) else ""
        hits.extend(
            Hit(number, " ".join(found.group().split()).lower())
            for found in pattern.finditer(f"{here}\n{following}")
            if found.start() < len(here)
        )
    return hits
