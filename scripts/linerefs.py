"""Find the places in a markdown text that cite a line of a file by its number."""
from __future__ import annotations

import re

import bannedwords
from sources import Problem, markdown_lines


_EXTENSIONS = r"py|spec|md|txt|json|toml|ya?ml|sh|bat"
# A path that ends in one of the extensions, or names the justfile, a LICENSE or a dotfile such as .gitignore.
# A bare extension such as `.py` names a kind of file, not a file.
_FILE = (
    rf"(?<![\w./-])(?:[\w./-]*\w\.(?i:{_EXTENSIONS})"
    rf"|(?:[\w.-]+/)*(?:justfile|LICENSE(?:\.MIT)?|\.(?!(?:{_EXTENSIONS})\b)[a-z][\w-]*))"
)
_LINES = r"(?i:lines?)\s+\d+(?:\s*(?:-|,|to|and)\s*\d+)*(?!\w)"
# What a file name may be wrapped in before "line N": backticks, bold, a link, then a comma or a colon.
_AFTER_FILE = r"[`*]*\]?(?:\([^)\s]*\))?[`*]*[,:]?\s+"
_ITEM = re.compile(r"[ \t]*(?:[-+*]|\d{1,9}[.)])(?:[ \t]|$)")
_CITATIONS = (
    re.compile(rf"(?P<cited>{_FILE}(?::\d+(?!\w)|#L\d+(?:-L\d+)?(?![\w-])))"),
    re.compile(rf"\((?P<cited>{_LINES})"),
    re.compile(rf"{_FILE}{_AFTER_FILE}(?P<cited>{_LINES})"),
    re.compile(rf"(?<!\w)(?P<cited>{_LINES})\s+(?:of|in)\s+[`*\[]*{_FILE}"),
)


def line_number_problems(name: str, text: str) -> list[Problem]:
    """Return a problem for each place outside code fences that cites a line of a file by its number.

    A citation is file:N, file#LN, "(line N", a file name before "line N", or "line N of" a file name.
    """
    found: dict[tuple[int, int], Problem] = {}
    for run in bannedwords.runs(markdown_lines(text)):
        for index, (number, line) in enumerate(run):
            # A citation may go on past the line break, but one list item does not go on into the next.
            following = run[index + 1][1] if index + 1 < len(run) else ""
            if _ITEM.match(line) and _ITEM.match(following):
                following = ""
            joined = f"{line} {following}"
            for pattern in _CITATIONS:
                for match in pattern.finditer(joined):
                    if match.start("cited") < len(line):
                        cited = " ".join(match.group("cited").split())
                        message = f'"{cited}" cites a line by its number, not its function or class'
                        found.setdefault((number, match.start("cited")), Problem(name, number, message))
    return [found[key] for key in sorted(found)]
