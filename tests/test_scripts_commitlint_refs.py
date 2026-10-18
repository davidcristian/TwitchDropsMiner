from __future__ import annotations

import pytest

import commitlint
from bannedwords import Table
from commitlint import Line
from gitrepo import commit, git, make_repo


@pytest.fixture
def repo(tmp_path):
    root = make_repo(tmp_path, {"a.py": "x = 1\n"})
    return root, commit(root)


def body(*texts: str, pasted: bool = False) -> list[Line]:
    return [Line(1, "fix: a", False), *(Line(number, text, pasted) for number, text in enumerate(texts, start=2))]


def test_is_commit_returns_true_for_the_full_and_the_short_hash_of_a_commit(repo):
    root, sha = repo
    assert commitlint.is_commit(sha, root) is True
    assert commitlint.is_commit(sha[:7], root) is True


def test_is_commit_returns_false_for_hex_that_names_no_commit(repo):
    root, sha = repo
    tree = git(root, "rev-parse", "HEAD^{tree}").strip()
    assert commitlint.is_commit("deadbeef00", root) is False
    assert commitlint.is_commit(tree, root) is False


def test_is_commit_returns_false_in_a_repo_without_commits(tmp_path):
    assert commitlint.is_commit("abcdef1", make_repo(tmp_path)) is False


@pytest.mark.parametrize(
    ("text", "label", "found"),
    [
        ("See ADR-0003 for why.", "a decision record number", "ADR-0"),
        ("As adr 12 says.", "a decision record number", "adr 1"),
        ("This closes task 5.", "a backlog task number", "task 5"),
        ("Both tasks 31 and 32.", "a backlog task number", "tasks 3"),
        ("Taken from PR 12.", "a pull request or issue number", "PR 1"),
        ("The pull request 9 had it.", "a pull request or issue number", "pull request 9"),
        ("Reported as issue 7.", "a pull request or issue number", "issue 7"),
        ("Fixes the crash in #45.", "an issue or pull request number", "#45"),
        ("It fails check 3 of AGENTS.md.", "a numbered item of a document", "check 3"),
        ("Do step 2 in README first.", "a numbered item of a document", "step 2"),
        ("As decision 4 says.", "a numbered item of a document", "decision 4"),
        ("See \u00a7 2.", "a numbered section", "\u00a7 2"),
    ],
)
def test_reference_problems_reports_a_numbered_pointer(repo, text, label, found):
    root, _ = repo
    assert commitlint.reference_problems(body(text), root) == [
        f"line 2 cites {label} ({found!r}); name the behavior instead"
    ]


@pytest.mark.parametrize(
    "text",
    ["The &#123; entity.", "The C#1 language.", "Retry 3 times with a backoff of 5 seconds.", "Use the 2nd task."],
)
def test_reference_problems_accepts_numbers_that_point_to_no_document(repo, text):
    root, _ = repo
    assert commitlint.reference_problems(body(text), root) == []


def test_reference_problems_reports_a_pointer_in_the_header_and_in_a_paste(repo):
    root, _ = repo
    lines = [Line(1, "fix: close task 7", False), Line(2, "", False), Line(3, "$ gh pr view 12 # see #12", True)]
    assert commitlint.reference_problems(lines, root) == [
        "line 1 cites a backlog task number ('task 7'); name the behavior instead",
        "line 3 cites an issue or pull request number ('#12'); name the behavior instead",
    ]


def test_reference_problems_reports_the_hash_of_a_real_commit_but_not_other_hex(repo):
    root, sha = repo
    lines = [*body(f"Undoes {sha[:7]}, not cafebabe1."), Line(3, f"$ git show {sha}", True)]
    assert commitlint.reference_problems(lines, root) == [
        f"line 2 cites the commit {sha[:7]!r}; name the change instead",
        f"line 3 cites the commit {sha!r}; name the change instead",
    ]


def pointer(text: str, line: int = 2) -> list[str]:
    return [f"line {line} cites a numbered item of a document ({text!r}); name the behavior instead"]


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("It is set in item 4.", "item 4"),
        ("Per decision 7, the list stays.", "decision 7"),
        ("Read section 4 first", "section 4"),
        ("Items 2 and 3 say it", "Items 2 and 3"),
        ("Both decisions 1, 2 or 5 hold", "decisions 1, 2 or 5"),
        ("Sections 2 to 4 say it", "Sections 2 to 4"),
        ("Items 2-4 say it", "Items 2-4"),
    ],
    ids=["item", "decision", "section", "plural items", "plural decisions", "plural sections", "a range"],
)
def test_pointer_problems_reports_decision_item_or_section_and_a_number_wherever_it_stands(text, found):
    assert commitlint.pointer_problems(body(text)) == pointer(found)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("As check 3 says", "check 3"),
        ("Then see step 2 below.", "step 2"),
        ("As `check 3` says, the list stays.", "check 3"),
        ('As "check 3" says.', "check 3"),
        ("It fails check 3 in AGENTS.md", "check 3"),
        ("Do step 2 of docs/building.md#run-the-checks now", "step 2"),
        ("It fails check 3 of README now", "check 3"),
        ("It fails `check 3` in AGENTS now", "check 3"),
        ("It fails check 3 of the AGENTS.md list", "check 3"),
        ("Follow steps 2-4 of AGENTS.md.", "steps 2-4"),
        ("Run steps 2 through 4 of docs/building.md.", "steps 2 through 4"),
        ("As checks 3 and 4 say", "checks 3 and 4"),
    ],
    ids=[
        "after as", "after see", "in backticks after as", "in quotes after as", "in and a markdown file",
        "of and a path into docs", "of README", "in AGENTS after backticks", "of the and a doc", "a range",
        "through", "plural and two numbers",
    ],
)
def test_pointer_problems_reports_check_or_step_after_as_or_see_or_before_a_doc_name(text, found):
    assert commitlint.pointer_problems(body(text)) == pointer(found)


@pytest.mark.parametrize(
    "text",
    [
        "Check 20 channels in one request.",
        "Both loops check 20 channels per request.",
        "Fetch the campaigns and check 20 channels per request.",
        "Retry the check 3 times before giving up.",
        "Check 3 of the 20 channels",
        "Wait, then check 2.5 seconds later.",
        "It fails check 3 of agents twice",
        "Read AGENTS.md, then check 3 in the list of checks.",
        "It fails check 3.",
    ],
    ids=[
        "a count", "after a noun", "after and", "after the", "of and a word that names no doc", "a decimal",
        "of and a lowercase agents", "in and a word that names no doc", "no as, see or doc",
    ],
)
def test_pointer_problems_accepts_check_or_step_and_a_number_without_as_see_or_a_doc_name(text):
    assert commitlint.pointer_problems(body(text)) == []


def test_pointer_problems_accepts_a_word_and_a_number_in_two_aligned_table_columns():
    assert commitlint.pointer_problems(body("join two list items      1 of 47 tests fail")) == []
    assert commitlint.pointer_problems(body("as check       3 of README.md")) == []


def test_pointer_problems_reads_a_paragraph_across_its_line_breaks():
    assert commitlint.pointer_problems(body("Both loops now check 20", "channels per request.")) == []
    assert commitlint.pointer_problems(body("It is wrong, see decision", "7 of the docs layout.")) == pointer(
        "decision 7"
    )
    assert commitlint.pointer_problems(body("It is wrong, as", "check 3 says.")) == pointer("check 3", line=3)


def test_pointer_problems_does_not_join_two_paragraphs():
    assert commitlint.pointer_problems(body("It is wrong, as", "", "check 3 runs first.")) == []


def test_pointer_problems_reports_a_pointer_that_two_rules_find_once():
    assert commitlint.pointer_problems(body("See check 3 in AGENTS.md.")) == pointer("check 3")


def test_pointer_problems_reports_a_pointer_in_the_header_and_in_a_paste():
    lines = [Line(1, "fix: follow decision 7", False), Line(2, "", False), Line(3, "$ grep 'see step 2' x", True)]
    assert commitlint.pointer_problems(lines) == [*pointer("decision 7", line=1), *pointer("step 2", line=3)]


def test_reference_problems_includes_the_pointers(repo):
    root, _ = repo
    assert commitlint.reference_problems(body("As check 3 says, task 4 is open."), root) == [
        "line 2 cites a backlog task number ('task 4'); name the behavior instead",
        *pointer("check 3"),
    ]


def test_reference_problems_accepts_a_count_in_the_subject(repo):
    root, _ = repo
    assert commitlint.reference_problems([Line(1, "perf: check 20 channels per request", False)], root) == []


def test_check_reports_a_reference_and_a_hash_through_the_whole_message(repo):
    root, sha = repo
    table = Table(("x" * 30,), 1, 1)
    text = f"revert: undo {sha[:8]}\n\nThe change in ADR-0002 broke the reload.\n"
    assert commitlint.check(text, table, root) == [
        f"line 1 cites the commit {sha[:8]!r}; name the change instead",
        "line 3 cites a decision record number ('ADR-0'); name the behavior instead",
    ]
