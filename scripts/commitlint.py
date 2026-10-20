"""Check a commit message against the commit rules in AGENTS.md that a script can read."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import bannedwords
from linerefs import FILE
from sources import DASHES, FENCES, ROOT


MAX_SUBJECT = 72
MAX_WIDTH = 72
MAX_WORDS = 50
EXEMPT = ("Merge ", "Revert \"", "fixup! ", "squash! ", "amend! ")
SCISSORS = "# ------------------------ >8 ------------------------"
_HEADER = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?: (?P<subject>.+)")
_PROMPT = re.compile(r"\s*\$ \S")
_HEX = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
# Trailer keys that git, GitHub and Conventional Commits write. A last paragraph of only these is data, not prose.
TRAILER_KEYS = (
    "BREAKING CHANGE", "BREAKING-CHANGE", "Signed-off-by", "Co-authored-by", "Reviewed-by", "Acked-by", "Tested-by",
    "Reported-by", "Suggested-by", "Helped-by", "Refs", "Cc",
)
_TRAILER = re.compile(rf"(?:{'|'.join(map(re.escape, TRAILER_KEYS))}): \S", re.IGNORECASE)
_DASHES = (
    *((re.compile(dash), label) for dash, label in DASHES.items()),
    (re.compile(r"(?<!\S)--(?!\S)"), "a spaced --"),
)
# A line of only hyphens and spaces, such as a markdown rule, is not a sentence.
_RULE = re.compile(r"[\s-]*")
_NUMBERS = r"\d+(?:(?:\s*[,-]\s*|\s+(?:and|or|to|through)\s+)\d+)*"
_STEP = rf"(?:check|step)s? {_NUMBERS}"
_DOC = r"(?:\S*\.md\b|(?-i:AGENTS|README)\b|docs/)"
# "decision 7" always points into a document. "check 3" does only after "as" or "see", or before "in" or "of"
# and a doc name, so that a count such as "check 20 channels" passes. "line 4" does only before "in" or "of" and
# a file name. Aligned table columns are not pointers.
_POINTERS = (
    re.compile(rf"\b(?P<ref>(?:decision|item|rule|section)s? {_NUMBERS})", re.IGNORECASE),
    re.compile(rf"\b(?:as|see)\s+[`'\"]?(?P<ref>{_STEP})", re.IGNORECASE),
    re.compile(rf"\b(?P<ref>{_STEP})[`'\"]?\s+(?:in|of)\s+(?:the\s+)?{_DOC}", re.IGNORECASE),
    re.compile(rf"\b(?P<ref>lines? {_NUMBERS})\s+(?:in|of)\s+(?:the\s+)?[`*\[]*(?:{FILE}|{_DOC})", re.IGNORECASE),
)
_VOLATILE = (
    (re.compile(r"\bADRs?[-\s]?\d", re.IGNORECASE), "a decision record number"),
    (re.compile(r"\btasks?\s*#?\d", re.IGNORECASE), "a backlog task number"),
    (re.compile(r"\b(?:PRs?|pull requests?|issues?)\s*#?\d", re.IGNORECASE), "a pull request or issue number"),
    (re.compile(r"(?:[\w.-]+/[\w.-]+|(?<![\w&]))#\d+\b"), "an issue or pull request number"),
    (re.compile("\u00a7\\s*\\d"), "a numbered section"),
)


class Line(NamedTuple):
    """One line of a message, and whether it is pasted output rather than the author's prose."""

    number: int
    text: str
    pasted: bool


def message_lines(text: str, edited: bool) -> list[str]:
    """Return the lines git keeps: an edited message loses its comment lines and everything below the scissors line."""
    if not edited:
        return text.splitlines()
    text = text.split(SCISSORS, 1)[0]
    return [line for line in text.splitlines() if not line.startswith("#")]


def is_fence(number: int, text: str) -> bool:
    """Whether a line opens or closes a code fence; the header never does."""
    return number > 1 and text.lstrip().startswith(FENCES)


def classify(lines: list[str]) -> tuple[list[Line], int | None]:
    """Mark each body line as pasted or not, and return the line of a fence nothing closes."""
    classified: list[Line] = []
    opened: int | None = None
    for number, text in enumerate(lines, start=1):
        fence = is_fence(number, text)
        if fence:
            opened = None if opened is not None else number
        pasted = fence or opened is not None or bool(_PROMPT.match(text))
        classified.append(Line(number, text, number > 1 and pasted))
    return classified, opened


def header_problems(header: str) -> list[str]:
    """Return the problems in the first line of a message that conventional-pre-commit does not check."""
    match = _HEADER.fullmatch(header)
    if match is None:
        return []
    problems: list[str] = []
    if len(header) > MAX_SUBJECT:
        problems.append(f"the subject line is {len(header)} characters; the limit is {MAX_SUBJECT}")
    subject = match.group("subject")
    if subject[0].isupper():
        problems.append("the subject starts with a capital letter")
    if subject.rstrip().endswith("."):
        problems.append("the subject ends with a period")
    if match.group("scope") == match.group("type"):
        problems.append(f"the scope repeats the type {match.group('type')!r}")
    return problems


def too_wide(text: str) -> bool:
    """Whether a line is over the width and has more than one word, so it can break between two of them."""
    return len(text) > MAX_WIDTH and len(text.split()) > 1


def trailers(lines: list[Line]) -> set[int]:
    """Return the line numbers of the last paragraph of the body when every line of it is a trailer."""
    last: list[Line] = []
    gap = False
    for line in lines[1:]:
        if not line.text.strip():
            gap = True
        elif gap:
            last, gap = [line], False
        else:
            last.append(line)
    return {line.number for line in last} if last and all(_TRAILER.match(line.text) for line in last) else set()


def body_problems(lines: list[Line], opened: int | None) -> list[str]:
    """Return the width, word count and dash problems of the lines that are not pasted."""
    own = [line for line in lines[1:] if not line.pasted]
    problems = [
        f"line {line.number} is {len(line.text)} characters; the body wraps at {MAX_WIDTH}"
        for line in own
        if too_wide(line.text)
    ]
    footer = trailers(lines)
    words = sum(len(line.text.split()) for line in own if line.number not in footer)
    if words > MAX_WORDS:
        problems.append(f"the body is {words} words; the limit is {MAX_WORDS}")
    if opened is not None:
        problems.append(f"line {opened} opens a code fence that nothing closes")
    problems.extend(dash_problems([lines[0], *own]))
    return problems


def prose_texts(lines: list[Line]) -> dict[int, str]:
    """Return the text of each line that is not blank, with code spans, link targets and URLs blanked out."""
    texts: dict[int, str] = {}
    # A code span may cross a line break, so the lines are masked in runs, as word_problems reads them.
    for run in bannedwords.runs((line.number, line.text) for line in lines):
        masked = bannedwords.mask("\n".join(text for _, text in run)).split("\n")
        texts.update(zip((number for number, _ in run), masked))
    return texts


def dash_problems(lines: list[Line]) -> list[str]:
    """Return each kind of dash on each line that is outside a code span, a link target and a URL."""
    texts = {line.number: line.text for line in lines}
    return [
        f"line {number} uses {label}; restructure the sentence"
        for number, prose in prose_texts(lines).items()
        if not _RULE.fullmatch(texts[number])
        for pattern, label in _DASHES
        if any(prose.startswith(found.group(), found.start()) for found in pattern.finditer(texts[number]))
    ]


def is_commit(token: str, repo: Path) -> bool:
    """Whether a hex string names a commit in the repo."""
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{token}^{{commit}}"], capture_output=True, check=False
    )
    return result.returncode == 0


def pointer_problems(lines: list[Line]) -> list[str]:
    """Return each pointer to a numbered item of a document, read across the line breaks of each paragraph."""
    found: dict[tuple[int, int], tuple[int, str]] = {}
    for run in bannedwords.runs((line.number, line.text) for line in lines):
        joined = " ".join(text for _, text in run)
        starts = [0]
        for _, text in run[:-1]:
            starts.append(starts[-1] + len(text) + 1)
        for pattern in _POINTERS:
            for match in pattern.finditer(joined):
                index = max(i for i, start in enumerate(starts) if start <= match.start("ref"))
                found.setdefault((run[0][0], match.start("ref")), (run[index][0], match.group("ref")))
    return [
        f"line {number} cites a numbered item of a document ({' '.join(ref.split())!r}); name the behavior instead"
        for _, (number, ref) in sorted(found.items())
    ]


def reference_problems(lines: list[Line], repo: Path) -> list[str]:
    """Return each numbered reference and commit hash, in a paste too, since a rewrite breaks both."""
    problems: list[str] = []
    for line in lines:
        for pattern, label in _VOLATILE:
            found = pattern.search(line.text)
            if found:
                problems.append(f"line {line.number} cites {label} ({found.group()!r}); name the behavior instead")
        problems.extend(
            f"line {line.number} cites the commit {token!r}; name the change instead"
            for token in _HEX.findall(line.text)
            if is_commit(token, repo)
        )
    problems.extend(pointer_problems(lines))
    return problems


def word_problems(lines: list[Line], table: bannedwords.Table) -> list[str]:
    """Return each banned word, in a paste too."""
    pattern = bannedwords.compile_words(table.words)
    # A fence line ends a run, so that a code span inside the paste does not start at the fence's backticks.
    texts = [(line.number, line.text) for line in lines if not is_fence(line.number, line.text)]
    return [
        f'line {hit.line} uses the banned word "{hit.word}"; the table in AGENTS.md gives a replacement'
        for run in bannedwords.runs(texts)
        for hit in bannedwords.find_words(run, pattern)
    ]


def check(text: str, table: bannedwords.Table, repo: Path, edited: bool) -> list[str]:
    """Return every problem in one commit message; edited says whether git opened an editor for it."""
    lines = message_lines(text, edited)
    header = lines[0] if lines else ""
    if header.startswith(EXEMPT):
        return []
    classified, opened = classify(lines)
    problems = header_problems(header)
    if classified:
        problems.extend(body_problems(classified, opened))
    problems.extend(reference_problems(classified, repo))
    problems.extend(word_problems(classified, table))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message_file", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    table = bannedwords.parse_table((args.root / "AGENTS.md").read_text(encoding="utf-8"))
    # git runs the hook with GIT_EDITOR=: when no editor opens, and then keeps the lines that start with "#".
    edited = os.environ.get("GIT_EDITOR") != ":"
    problems = check(args.message_file.read_text(encoding="utf-8"), table, args.root, edited)
    for problem in problems:
        print(f"commitlint: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
