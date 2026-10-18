from __future__ import annotations

import pytest

import docscheck
from bannedwords import compile_words
from gitrepo import AGENTS, BEARING, HANGING, HOOD, SEAM, make_repo
from sources import Problem

BANNED = compile_words([SEAM, BEARING, HANGING, HOOD])
SECTIONS = ["Context", "Decision", "Consequences", "Alternatives rejected", "Related"]


def adr(title: str = "ADR-0001: One decision", status: str = "Accepted (2026-10-18)", sections=SECTIONS) -> str:
    body = "".join(f"## {section}\n\nText.\n\n" for section in sections)
    return f"# {title}\n\n**Status:** {status}\n\n{body}"


def task(title: str = "A thing is slow", status: str = "open", skip: str = "") -> str:
    fields = {
        "Status": f"**Status:** {status}",
        "Area": "**Area:** twitch",
        "Origin": "**Origin:** found by hand",
        "Verified": "**Verified:** 2026-10-18",
        "History": "## History\n\n- 2026-10-18: Opened.",
    }
    lines = [line for field, line in fields.items() if field != skip]
    return f"# {title}\n\n" + "\n".join(lines[:-1]) + "\n\nBody.\n\n" + lines[-1] + "\n"


def docs() -> dict[str, str]:
    return {
        "AGENTS.md": AGENTS,
        "docs/index.md": (
            "# Docs index\n\n## Decisions\n\n"
            "| Record | What |\n| --- | --- |\n"
            "| [ADR-0001: One decision](adr/ADR-0001-one-decision.md) | x |\n\n"
            "## Modules\n\n- [main.py](modules/main.md#purpose)\n"
        ),
        "docs/adr/ADR-0001-one-decision.md": adr(),
        "docs/adr/README.md": "# Decision records\n",
        "docs/modules/main.md": "# `main.py`\n\n## Purpose\n",
        "docs/refinements/index.md": (
            "# Deferred refinements\n\n| Task | Area |\n| --- | --- |\n"
            "| [001: A thing is slow](tasks/001-a-thing-is-slow.md) | twitch |\n"
        ),
        "docs/refinements/tasks/001-a-thing-is-slow.md": task(),
    }


def test_index_problems_accepts_an_index_that_links_each_record_by_its_title():
    texts = docs()
    assert docscheck.index_problems(docscheck.DOCS_INDEX, docscheck.ADR_NAME, texts, "decision record") == []
    assert docscheck.index_problems(docscheck.TASKS_INDEX, docscheck.TASK_NAME, texts, "task") == []
    assert docscheck.index_problems(docscheck.DOCS_INDEX, docscheck.MODULE_NAME, texts, "module") == []


def test_index_problems_reports_a_record_the_index_does_not_link():
    texts = docs()
    texts["docs/adr/ADR-0002-two.md"] = adr("ADR-0002: Two")
    assert docscheck.index_problems(docscheck.DOCS_INDEX, docscheck.ADR_NAME, texts, "decision record") == [
        Problem("docs/index.md", 1, "no link to docs/adr/ADR-0002-two.md")
    ]


def test_index_problems_reports_link_text_that_is_not_the_title():
    texts = docs()
    texts["docs/refinements/index.md"] = "| [1: A thing is slow](tasks/001-a-thing-is-slow.md) | twitch |\n"
    assert docscheck.index_problems(docscheck.TASKS_INDEX, docscheck.TASK_NAME, texts, "task") == [
        Problem("docs/refinements/index.md", 1, "link text is not the task title '001: A thing is slow'")
    ]


def test_index_problems_accepts_any_link_text_for_a_module_doc_but_needs_the_link():
    texts = docs()
    texts["docs/modules/gui.md"] = "# `gui.py`\n"
    assert docscheck.index_problems(docscheck.DOCS_INDEX, docscheck.MODULE_NAME, texts, "module") == [
        Problem("docs/index.md", 1, "no link to docs/modules/gui.md")
    ]


def test_index_problems_reports_every_record_when_the_index_is_missing():
    texts = docs()
    del texts["docs/refinements/index.md"]
    assert docscheck.index_problems(docscheck.TASKS_INDEX, docscheck.TASK_NAME, texts, "task") == [
        Problem("docs/refinements/index.md", 1, "no link to docs/refinements/tasks/001-a-thing-is-slow.md")
    ]


@pytest.mark.parametrize("status", ["Accepted (2026-10-18)", "Superseded by ADR-0007"])
def test_adr_problems_accepts_a_record_in_the_format(status):
    assert docscheck.adr_problems("docs/adr/ADR-0001-x.md", adr(status=status), "0001") == []


def test_adr_problems_reports_a_title_without_the_number_of_the_file():
    assert docscheck.adr_problems("docs/adr/ADR-0003-x.md", adr("ADR-0001: One"), "0003") == [
        Problem("docs/adr/ADR-0003-x.md", 1, "the title does not start with 'ADR-0003: '")
    ]


@pytest.mark.parametrize("status", ["Accepted", "Accepted (18 October 2026)", "Proposed (2026-10-18)", "Superseded"])
def test_adr_problems_reports_a_status_line_not_in_the_format(status):
    assert docscheck.adr_problems("a.md", adr(status=status), "0001") == [
        Problem("a.md", 1, "no Status line of the form in docs/adr/README.md")
    ]


@pytest.mark.parametrize(
    "sections",
    [
        ["Decision", "Context", "Consequences", "Alternatives rejected", "Related"],
        SECTIONS[:-1],
        [*SECTIONS, "History"],
    ],
    ids=["out of order", "one missing", "one extra"],
)
def test_adr_problems_reports_sections_that_differ_from_the_format(sections):
    assert docscheck.adr_problems("a.md", adr(sections=sections), "0001") == [
        Problem("a.md", 1, f"the sections are {sections}, not {SECTIONS}")
    ]


def test_adr_problems_ignores_a_section_heading_inside_a_fence():
    text = adr() + "```\n## Extra\n```\n"
    assert docscheck.adr_problems("a.md", text, "0001") == []


@pytest.mark.parametrize("status", ["open", "done 2026-10-18", "declined 2026-01-02", "satisfied 2026-12-31"])
def test_task_problems_accepts_a_task_in_the_format(status):
    assert docscheck.task_problems("t.md", task(status=status), "a-thing", BANNED) == []


@pytest.mark.parametrize("status", ["done", "closed 2026-10-18", "Open"])
def test_task_problems_reports_a_status_not_in_the_format(status):
    assert docscheck.task_problems("t.md", task(status=status), "a-thing", BANNED) == [
        Problem("t.md", 1, "no Status line: open, or done, declined or satisfied with a date")
    ]


@pytest.mark.parametrize("field", ["Area", "Origin", "Verified"])
def test_task_problems_reports_a_missing_field(field):
    assert docscheck.task_problems("t.md", task(skip=field), "a-thing", BANNED) == [
        Problem("t.md", 1, f"no {field} line in the task format")
    ]


def test_task_problems_reports_a_missing_title_and_a_missing_history():
    text = task(skip="History").replace("# A thing is slow\n", "")
    assert docscheck.task_problems("t.md", text, "a-thing", BANNED) == [
        Problem("t.md", 1, "no title"),
        Problem("t.md", 1, "no History section"),
    ]


def test_task_problems_reports_a_banned_word_in_the_file_name():
    assert docscheck.task_problems("t.md", task(), f"fix-the-{SEAM}-checks", BANNED) == [
        Problem("t.md", 1, f'the file name uses the banned word "{SEAM}"')
    ]


@pytest.mark.parametrize("word", [BEARING, HANGING])
def test_task_problems_reports_a_hyphenated_banned_word_in_the_file_name(word):
    assert docscheck.task_problems("t.md", task(), f"{word}-checks", BANNED) == [
        Problem("t.md", 1, f'the file name uses the banned word "{word}"')
    ]


@pytest.mark.parametrize(
    ("slug_words", "word"),
    [
        (f"fix-the-{BEARING}-checks", BEARING),
        (f"why-{HOOD.replace(' ', '-')}-fails", HOOD),
        (f"{SEAM}-and-{BEARING}", SEAM),
        ("a-thing-is-slow", ""),
    ],
    ids=["inside the name", "a phrase joined by hyphens", "the first of two", "none"],
)
def test_banned_in_name_returns_the_first_banned_word_the_file_name_forms(slug_words, word):
    assert docscheck.banned_in_name(slug_words, BANNED) == word


def test_record_problems_reports_a_number_two_records_of_one_folder_use():
    texts = docs()
    texts["docs/adr/ADR-0001-again.md"] = adr()
    texts["docs/refinements/tasks/001-again.md"] = task()
    texts["docs/refinements/tasks/0001-not-a-task.md"] = "# Not checked\n"
    assert docscheck.record_problems(texts, BANNED) == [
        Problem("docs/adr/ADR-0001-one-decision.md", 1, "its number is also used by docs/adr/ADR-0001-again.md"),
        Problem("docs/refinements/tasks/001-again.md", 1,
                "its number is also used by docs/refinements/tasks/001-a-thing-is-slow.md"),
    ]


def test_check_returns_no_problem_for_docs_in_the_format(tmp_path):
    root = make_repo(tmp_path, {**docs(), "lang/notes.md": "[x](gone.md)\n"})
    assert docscheck.check(root) == (7, [])


def test_check_reports_link_index_and_format_problems_in_order(tmp_path):
    files = docs()
    files["docs/adr/ADR-0001-one-decision.md"] = adr(sections=SECTIONS[:2]) + "[x](gone.md)\n"
    files["docs/refinements/tasks/002-new.md"] = task("New")
    root = make_repo(tmp_path, files)
    assert [str(problem) for problem in docscheck.check(root)[1]] == [
        f"docs/adr/ADR-0001-one-decision.md:1: the sections are {SECTIONS[:2]}, not {SECTIONS}",
        "docs/adr/ADR-0001-one-decision.md:13: link to gone.md, which does not exist",
        "docs/refinements/index.md:1: no link to docs/refinements/tasks/002-new.md",
    ]


def test_check_reports_a_decision_record_whose_name_is_not_in_the_format(tmp_path):
    files = {**docs(), "docs/adr/adr-12-new-rule.md": "# New rule\n", "docs/refinements/tasks/36-new.md": task()}
    assert docscheck.check(make_repo(tmp_path, files))[1] == [
        Problem("docs/adr/adr-12-new-rule.md", 1, "the name is not in the form ADR-NNNN-slug.md"),
        Problem("docs/refinements/tasks/36-new.md", 1, "the name is not in the form NNN-slug.md"),
    ]


@pytest.mark.parametrize(
    ("name", "form"),
    [
        ("docs/adr/adr-0002-lower.md", "ADR-NNNN-slug.md"),
        ("docs/adr/ADR-02-short.md", "ADR-NNNN-slug.md"),
        ("docs/adr/ADR-0002-Upper.md", "ADR-NNNN-slug.md"),
        ("docs/adr/ADR-0002-text.txt", "ADR-NNNN-slug.md"),
        ("docs/adr/images/diagram.png", "ADR-NNNN-slug.md"),
        ("docs/refinements/tasks/1-short.md", "NNN-slug.md"),
        ("docs/refinements/tasks/0001-four.md", "NNN-slug.md"),
        ("docs/refinements/tasks/001_underscore.md", "NNN-slug.md"),
        ("docs/refinements/tasks/README.md", "NNN-slug.md"),
    ],
)
def test_name_problems_reports_a_file_in_a_record_folder_whose_name_is_not_in_its_format(name, form):
    assert docscheck.name_problems(["README.md", name]) == [Problem(name, 1, f"the name is not in the form {form}")]


def test_name_problems_accepts_records_in_the_format_the_adr_readme_and_files_in_other_folders():
    names = [
        "docs/adr/README.md", "docs/adr/ADR-0001-one-decision.md", "docs/refinements/tasks/001-a-thing-is-slow.md",
        "docs/refinements/index.md", "docs/index.md", "docs/modules/main.md", "docs/adr.md", "README.md",
    ]
    assert docscheck.name_problems(names) == []


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {**docs(), "README.md": "[x](gone.md)\n"})
    assert docscheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == (
        "README.md:1: link to gone.md, which does not exist\ndocscheck: 8 files, 1 problems\n"
    )


def test_main_returns_0_for_docs_in_the_format(tmp_path, capsys):
    root = make_repo(tmp_path, docs())
    assert docscheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "docscheck: 7 files, 0 problems\n"
