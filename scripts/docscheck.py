"""Fail on a broken link between docs, a line cited by number, or a record not in its index or its format."""
from __future__ import annotations

import argparse
import posixpath
import re
import sys
from collections.abc import Iterable
from pathlib import Path

import bannedwords
from linerefs import line_number_problems
from sources import ROOT, Line, Problem, markdown_lines, read_texts, repo_files


DOCS_INDEX = "docs/index.md"
TASKS_INDEX = "docs/refinements/index.md"
ADR_FOLDER = "docs/adr/"
ADR_README = "docs/adr/README.md"
TASKS_FOLDER = "docs/refinements/tasks/"
ADR_NAME = re.compile(r"docs/adr/ADR-(\d{4})-[a-z0-9-]+\.md")
MODULE_NAME = re.compile(r"docs/modules/[a-z0-9_-]+\.md")
TASK_NAME = re.compile(r"docs/refinements/tasks/(\d{3})-([a-z0-9-]+)\.md")
ADR_HEADINGS = ["Context", "Decision", "Consequences", "Alternatives rejected", "Related"]
ADR_STATUS = re.compile(r"\*\*Status:\*\* (Accepted \(\d{4}-\d{2}-\d{2}\)|Superseded by ADR-\d{4})")
TASK_STATUS = re.compile(r"\*\*Status:\*\* (open|(done|declined|satisfied) \d{4}-\d{2}-\d{2})")
TASK_FIELDS = {
    "Area": re.compile(r"\*\*Area:\*\* \S.*"),
    "Origin": re.compile(r"\*\*Origin:\*\* \S.*"),
    "Verified": re.compile(r"\*\*Verified:\*\* \d{4}-\d{2}-\d{2}"),
}
_TEXT = r"(?:[^\[\]`]|`[^`]*`)"
# The text may hold brackets one level deep, as an image does, and the target may be in <> and have a title.
_LINK = re.compile(rf"\[((?:{_TEXT}|\[{_TEXT}*\])*)\]\(\s*(?:<([^<>\n]*)>|([^)\s]+))"
                   r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
# A label that starts with ^ is a footnote, whose text is not a link target.
_DEFINITION = re.compile(r" {0,3}\[(?!\^)(?:[^\]\\]|\\.)+\]:[ \t]*(?:<([^<>]*)>|(\S+))(?:[ \t]+[\"'(].*)?")
_CODE_SPAN = re.compile(r"`[^`]*`")
_HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*$")
_UNDERLINE = re.compile(r" {0,3}(=+|-+)[ \t]*")
_BREAK = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*")
_MARKER = r"(?:[-+*]|\d{1,9}[.)])(?:[ \t]|$)"
# A table row, a block quote or a list item, whose following lines continue it and cannot be a heading's text.
_BLOCK = re.compile(rf" {{0,3}}(?:[|>]|{_MARKER})")
# A URL: a scheme of two or more letters, so that a Windows drive such as C: is read as a path, or a leading //.
_URL = re.compile(r"[a-z][a-z0-9+.-]+:|//", re.IGNORECASE)


def slug(heading: str) -> str:
    """Return the anchor GitHub gives a heading, before a repeated heading's number is added."""
    text = _CODE_SPAN.sub(lambda found: found.group()[1:-1], heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def headings(text: str) -> list[tuple[int, int, str]]:
    """Return each heading outside code, with # or underlined, as its line number, its level and its text."""
    found: list[tuple[int, int, str]] = []
    paragraph: list[Line] = []
    blocked = False
    previous = 0
    for number, line in markdown_lines(text):
        # A gap in the numbers is a fenced block, which ends the paragraph before it.
        if number != previous + 1:
            paragraph, blocked = [], False
        previous = number
        atx, underline = _HEADING.fullmatch(line), _UNDERLINE.fullmatch(line)
        if underline and paragraph:
            words = " ".join(part.strip() for _, part in paragraph)
            found.append((paragraph[0][0], 1 if underline.group(1)[0] == "=" else 2, words))
            paragraph = []
        elif atx or not line.strip() or _BREAK.fullmatch(line):
            if atx:
                found.append((number, len(atx.group(1)), atx.group(2)))
            paragraph, blocked = [], False
        elif blocked or _BLOCK.match(line):
            paragraph, blocked = [], True
        elif paragraph or not line.startswith(("    ", "\t")):
            paragraph.append((number, line))
    return found


def anchors(text: str) -> set[str]:
    """Return the anchors GitHub gives the headings of a markdown text."""
    found: set[str] = set()
    counts: dict[str, int] = {}
    for _, _, words in headings(text):
        base = slug(words)
        count = counts.get(base, 0)
        counts[base] = count + 1
        found.add(base if count == 0 else f"{base}-{count}")
    return found


def links(text: str) -> list[tuple[int, str, str]]:
    """Return each link outside code as its line number, its text and its target."""
    found: list[tuple[int, str, str]] = []
    for number, line in markdown_lines(text):
        spans = [match.span() for match in _CODE_SPAN.finditer(line)]
        outer = list(_LINK.finditer(line))
        inner = [image for match in outer for image in _LINK.finditer(line, match.start(1), match.end(1))]
        for match in sorted(outer + inner, key=lambda match: match.start()):
            if not any(start <= match.start() < end for start, end in spans):
                found.append((number, match.group(1), match.group(2) or match.group(3) or ""))
    return found


def definitions(text: str) -> list[tuple[int, str]]:
    """Return each link reference definition outside code, such as [map]: x.md, as its line number and target."""
    matches = [(number, _DEFINITION.fullmatch(line)) for number, line in markdown_lines(text)]
    return [(number, match.group(1) or match.group(2) or "") for number, match in matches if match]


def resolve(name: str, target: str) -> tuple[str, str]:
    """Return the repo path and the anchor that a link in the file at name points to, as GitHub resolves it."""
    path, _, anchor = target.partition("#")
    if not path:
        return name, anchor
    # GitHub resolves a path that starts with / against the repo root.
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(name), path)
    return posixpath.normpath(joined), anchor


def known_paths(files: Iterable[str]) -> set[str]:
    """Return the repo root ".", each of the files, and each folder that holds one of them."""
    return {"."} | {name.rsplit("/", depth)[0] for name in files for depth in range(name.count("/") + 1)}


def link_problems(name: str, texts: dict[str, str], paths: set[str]) -> list[Problem]:
    """Return a problem for each link in one file to a path not in paths, or to a heading that does not exist."""
    text = texts[name]
    targets = sorted([(number, target) for number, _, target in links(text)] + definitions(text), key=lambda x: x[0])
    problems: list[Problem] = []
    for number, target in targets:
        if _URL.match(target):
            continue
        path, anchor = resolve(name, target)
        if path not in paths:
            problems.append(Problem(name, number, f"link to {target}, which does not exist"))
        elif anchor and path in texts and anchor not in anchors(texts[path]):
            problems.append(Problem(name, number, f"link to {target}, whose heading does not exist"))
    return problems


def title(text: str) -> str:
    """Return the text of a document's first heading of level 1, or an empty string."""
    return next((words for _, level, words in headings(text) if level == 1), "")


def index_problems(index: str, pattern: re.Pattern[str], texts: dict[str, str], label: str) -> list[Problem]:
    """Return the records an index does not link, and its links whose text is not the record's title."""
    linked: dict[str, tuple[int, str]] = {}
    for number, words, target in links(texts.get(index, "")):
        linked.setdefault(resolve(index, target)[0], (number, words))
    problems: list[Problem] = []
    for name in sorted(texts):
        match = pattern.fullmatch(name)
        if match is None:
            continue
        if name not in linked:
            problems.append(Problem(index, 1, f"no link to {name}"))
            continue
        expected = title(texts[name])
        if label == "task":
            expected = f"{match.group(1)}: {expected}"
        if label != "module" and linked[name][1] != expected:
            problems.append(Problem(index, linked[name][0], f"link text is not the {label} title {expected!r}"))
    return problems


def adr_problems(name: str, text: str, number: str) -> list[Problem]:
    """Return how one decision record differs from the format in docs/adr/README.md."""
    problems: list[Problem] = []
    if not title(text).startswith(f"ADR-{number}: "):
        problems.append(Problem(name, 1, f"the title does not start with 'ADR-{number}: '"))
    if not any(ADR_STATUS.fullmatch(line) for _, line in markdown_lines(text)):
        problems.append(Problem(name, 1, "no Status line of the form in docs/adr/README.md"))
    found = [words for _, level, words in headings(text) if level == 2]
    if found != ADR_HEADINGS:
        problems.append(Problem(name, 1, f"the sections are {found}, not {ADR_HEADINGS}"))
    return problems


def banned_in_name(slug_words: str, banned: re.Pattern[str]) -> str:
    """Return the first banned word that consecutive words of a file name form, joined by hyphens or spaces."""
    parts = slug_words.split("-")
    for start in range(len(parts)):
        for end in range(len(parts), start, -1):
            for joined in ("-".join(parts[start:end]), " ".join(parts[start:end])):
                if banned.fullmatch(joined):
                    return joined
    return ""


def task_problems(name: str, text: str, slug_words: str, banned: re.Pattern[str]) -> list[Problem]:
    """Return how one task file differs from the format in docs/refinements/index.md."""
    lines = [line for _, line in markdown_lines(text)]
    problems: list[Problem] = []
    if not title(text):
        problems.append(Problem(name, 1, "no title"))
    if not any(TASK_STATUS.fullmatch(line) for line in lines):
        problems.append(Problem(name, 1, "no Status line: open, or done, declined or satisfied with a date"))
    for field, pattern in TASK_FIELDS.items():
        if not any(pattern.fullmatch(line) for line in lines):
            problems.append(Problem(name, 1, f"no {field} line in the task format"))
    if "## History" not in lines:
        problems.append(Problem(name, 1, "no History section"))
    found = banned_in_name(slug_words, banned)
    if found:
        problems.append(Problem(name, 1, f'the file name uses the banned word "{found}"'))
    return problems


def name_problems(files: Iterable[str]) -> list[Problem]:
    """Return a problem for each file in the decision record or task folder whose name is not in its format."""
    problems: list[Problem] = []
    for name in files:
        if name.startswith(ADR_FOLDER) and name != ADR_README and not ADR_NAME.fullmatch(name):
            problems.append(Problem(name, 1, "the name is not in the form ADR-NNNN-slug.md"))
        elif name.startswith(TASKS_FOLDER) and not TASK_NAME.fullmatch(name):
            problems.append(Problem(name, 1, "the name is not in the form NNN-slug.md"))
    return problems


def record_problems(texts: dict[str, str], banned: re.Pattern[str]) -> list[Problem]:
    """Return the format problems of every decision record and task file, and repeated numbers."""
    problems: list[Problem] = []
    numbers: dict[str, str] = {}
    for name, text in sorted(texts.items()):
        adr, task = ADR_NAME.fullmatch(name), TASK_NAME.fullmatch(name)
        if adr:
            problems.extend(adr_problems(name, text, adr.group(1)))
        elif task:
            problems.extend(task_problems(name, text, task.group(2), banned))
        else:
            continue
        key = name.rsplit("/", 1)[0] + (adr or task).group(1)
        if key in numbers:
            problems.append(Problem(name, 1, f"its number is also used by {numbers[key]}"))
        numbers[key] = name
    return problems


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of markdown files read and every problem in them."""
    files = repo_files(root)
    markdown = [name for name in files if name.endswith(".md") and not name.startswith("lang/")]
    texts, problems = read_texts(root, markdown)
    table = bannedwords.parse_table(texts.get("AGENTS.md", ""))
    paths = known_paths(files)
    problems.extend(problem for name in texts for problem in link_problems(name, texts, paths))
    problems.extend(problem for name, text in texts.items() for problem in line_number_problems(name, text))
    problems.extend(index_problems(DOCS_INDEX, ADR_NAME, texts, "decision record"))
    problems.extend(index_problems(DOCS_INDEX, MODULE_NAME, texts, "module"))
    problems.extend(index_problems(TASKS_INDEX, TASK_NAME, texts, "task"))
    problems.extend(record_problems(texts, bannedwords.compile_words(table.words)))
    problems.extend(name_problems(files))
    return len(texts), sorted(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"docscheck: {count} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
