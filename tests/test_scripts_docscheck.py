from __future__ import annotations

import pytest

import docscheck
from gitrepo import AGENTS, make_repo, write
from sources import Problem, repo_files


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("What every change must pass", "what-every-change-must-pass"),
        ("A new setting?", "a-new-setting"),
        ("`gui.py` and [AGENTS.md](../AGENTS.md)", "guipy-and-agentsmd"),
        ("Fetch & claim", "fetch--claim"),
        ("snake_case and kebab-case", "snake_case-and-kebab-case"),
        ("Caf\u00e9 \U0001f310 menu", "caf\u00e9--menu"),
    ],
)
def test_slug_returns_the_anchor_github_gives_a_heading(heading, anchor):
    assert docscheck.slug(heading) == anchor


def test_headings_returns_the_line_level_and_text_of_each_heading():
    text = "# Title #\n\nbody\n### Deep   \n#hashtag\n####### seven\n```\n# comment\n```\n## End\n"
    assert docscheck.headings(text) == [(1, 1, "Title"), (4, 3, "Deep"), (10, 2, "End")]


def test_anchors_numbers_a_repeated_heading():
    text = "# Notes\n## Notes\n### Notes\n## Other\n"
    assert docscheck.anchors(text) == {"notes", "notes-1", "notes-2", "other"}


def test_anchors_includes_a_setext_heading():
    assert docscheck.anchors("Title\n=====\n\nPart\n----\n") == {"title", "part"}


def test_headings_returns_a_setext_heading_at_the_first_line_of_its_text():
    text = "# Top\n\nFirst part\nof the title  \n    indented end\n===\n\n## Next\nShort\n----\n"
    assert docscheck.headings(text) == [
        (1, 1, "Top"),
        (3, 1, "First part of the title indented end"),
        (8, 2, "Next"),
        (9, 2, "Short"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("| a | b |\n| --- | --- |\n| c | d |\n---\n", []),
        ("- item\n---\n", []),
        ("- item\nlazy text\n---\n", []),
        ("1. item\n===\n", []),
        ("> quote\n---\n", []),
        ("Text\n\n---\n", []),
        ("Text\n\n===\n", []),
        ("Text\n```\ncode\n```\n---\n", []),
        ("    indented code\n---\n", []),
        ("***\n---\n", []),
        ("# Top\n---\n", [(1, 1, "Top")]),
    ],
    ids=[
        "under a table row", "under a list item", "under a list item's next line", "under a numbered item",
        "under a quote", "after a blank line", "equals after a blank line", "after a fence",
        "under indented code", "under a break", "under a hash heading",
    ],
)
def test_headings_reads_an_underline_that_follows_no_paragraph_as_no_heading(text, expected):
    assert docscheck.headings(text) == expected


def test_links_returns_the_line_text_and_target_of_each_link_outside_code():
    text = (
        "See [a](x.md) and ![logo](img/logo.png).\n"
        "Not `[b](y.md)` here.\n"
        "```\n[c](z.md)\n```\n"
        "[`a]b` code](w.md#part)\n"
    )
    assert docscheck.links(text) == [
        (1, "a", "x.md"),
        (1, "logo", "img/logo.png"),
        (6, "`a]b` code", "w.md#part"),
    ]


def test_definitions_returns_the_line_and_target_of_each_reference_definition_outside_code():
    text = (
        "[map]: gone.md\n"
        '   [b]: <my file.md> "Title"\n'
        "[c]: x.md#part (Title)\n"
        "Text that ends\n[d]: after-text.md\n\n"
        "[e]: e.md not-a-title\n\n"
        "[^1]: footnote.md\n"
        "```\n[f]: f.md\n```\n"
        "[g]: g.md\n"
        "## Heading\n[h]: h.md\n"
    )
    assert docscheck.definitions(text) == [
        (1, "gone.md"),
        (2, "my file.md"),
        (3, "x.md#part"),
        (5, "after-text.md"),
        (13, "g.md"),
        (15, "h.md"),
    ]


@pytest.mark.parametrize(
    ("name", "target", "expected"),
    [
        ("docs/index.md", "adr/ADR-0001-x.md", ("docs/adr/ADR-0001-x.md", "")),
        ("docs/adr/ADR-0001-x.md", "../../AGENTS.md#prose", ("AGENTS.md", "prose")),
        ("docs/index.md", "#decisions", ("docs/index.md", "decisions")),
        ("README.md", "docs/./modules/", ("docs/modules", "")),
        ("README.md", "../other/x.md", ("../other/x.md", "")),
        ("docs/index.md", "../..", ("..", "")),
        ("docs/index.md", "/AGENTS.md#prose", ("AGENTS.md", "prose")),
        ("docs/index.md", "/", (".", "")),
        ("docs/index.md", "/../x.md", ("../x.md", "")),
    ],
)
def test_resolve_returns_the_repo_path_and_anchor_of_a_link(name, target, expected):
    assert docscheck.resolve(name, target) == expected


def test_known_paths_returns_the_root_each_file_and_each_folder_that_holds_one():
    assert docscheck.known_paths(["README.md", "docs/adr/ADR-0001-x.md"]) == {
        ".", "README.md", "docs", "docs/adr", "docs/adr/ADR-0001-x.md",
    }


@pytest.fixture
def repo(tmp_path):
    files = {
        "AGENTS.md": "# Rules\n\n## Prose\n\n## Prose\n",
        "docs/index.md": "# Index\n",
        "docs/modules/main.md": "# main\n",
        "tool.py": "x = 1\n",
    }
    root = make_repo(tmp_path / "repo", files)
    return root, {name: text for name, text in files.items() if name.endswith(".md")}


def problems_of(repo, text: str, name: str = "docs/index.md") -> list[Problem]:
    root, texts = repo
    write(root, {name: text})
    texts[name] = text
    return docscheck.link_problems(name, texts, docscheck.known_paths(repo_files(root)))


def test_link_problems_accepts_links_to_files_folders_headings_and_urls(repo):
    text = (
        "# Index\n\n[a](../AGENTS.md#prose-1) [b](modules/) [c](modules) [d](../tool.py#L1) [e](#index)\n"
        "[f](https://example.invalid/missing.md) [g](mailto:t@example.invalid) [h](..)\n"
    )
    assert problems_of(repo, text) == []


def test_link_problems_reports_a_missing_file_and_a_missing_folder(repo):
    assert problems_of(repo, "[a](modules/gone.md)\n\n[b](gone/)\n") == [
        Problem("docs/index.md", 1, "link to modules/gone.md, which does not exist"),
        Problem("docs/index.md", 3, "link to gone/, which does not exist"),
    ]


def test_link_problems_reports_a_missing_heading_in_another_file_and_in_the_same_file(repo):
    assert problems_of(repo, "[a](../AGENTS.md#prose-2)\n[b](#nothing)\n") == [
        Problem("docs/index.md", 1, "link to ../AGENTS.md#prose-2, whose heading does not exist"),
        Problem("docs/index.md", 2, "link to #nothing, whose heading does not exist"),
    ]


def test_link_problems_reports_a_link_that_leaves_the_repo_even_when_the_file_exists(repo):
    root, _ = repo
    (root.parent / "outside.md").write_text("# Outside\n")
    assert problems_of(repo, "[a](../../outside.md)\n") == [
        Problem("docs/index.md", 1, "link to ../../outside.md, which does not exist")
    ]


def test_link_problems_reports_a_link_to_the_folder_above_the_repo(repo):
    assert problems_of(repo, "[a](../..)\n") == [Problem("docs/index.md", 1, "link to ../.., which does not exist")]


def test_link_problems_reports_an_absolute_path_outside_the_repo(repo):
    root, _ = repo
    outside = root.parent / "outside.md"
    outside.write_text("# Outside\n")
    assert problems_of(repo, f"[a]({outside.as_posix()})\n") == [
        Problem("docs/index.md", 1, f"link to {outside.as_posix()}, which does not exist")
    ]


def test_link_problems_resolves_a_path_that_starts_with_a_slash_against_the_repo_root(repo):
    text = "[a](/AGENTS.md#prose-1) [b](/docs/modules/) [c](/tool.py)\n[d](/AGENTS.md#nothing) [e](/modules/main.md)\n"
    assert problems_of(repo, text) == [
        Problem("docs/index.md", 2, "link to /AGENTS.md#nothing, whose heading does not exist"),
        Problem("docs/index.md", 2, "link to /modules/main.md, which does not exist"),
    ]


def test_link_problems_reads_a_windows_drive_as_a_path_and_not_a_url(repo):
    assert problems_of(repo, "[a](C:/Users/x/outside.md)\n") == [
        Problem("docs/index.md", 1, "link to C:/Users/x/outside.md, which does not exist")
    ]


def test_check_reports_a_link_to_a_file_git_ignores(tmp_path):
    root = make_repo(tmp_path, {
        ".gitignore": "settings.json\n",
        "settings.json": "{}",
        "AGENTS.md": "# Rules\n\n| Do not write | Write instead |\n| --- | --- |\n| x | y |\n",
        "README.md": "[settings](settings.json)\n",
    })
    assert docscheck.check(root)[1] == [Problem("README.md", 1, "link to settings.json, which does not exist")]


def test_check_reports_a_link_to_a_folder_that_holds_only_files_git_ignores(tmp_path):
    root = make_repo(tmp_path, {
        ".gitignore": "cache/\n",
        "cache/image.png": b"\x89PNG",
        "docs/notes.md": "# Notes\n",
        "AGENTS.md": AGENTS,
        "README.md": "[a](cache/) [b](docs) [c](./)\n",
    })
    assert docscheck.check(root)[1] == [Problem("README.md", 1, "link to cache/, which does not exist")]


def test_check_reports_a_markdown_file_that_is_not_utf8_but_not_a_file_of_another_kind(tmp_path):
    root = make_repo(tmp_path, {
        "AGENTS.md": AGENTS,
        "docs/notes.md": "# Notes\n\nSee [gone](gone.md) \u2014 here.\n".encode("cp1252"),
        "notes.txt": b"\xff",
        "lang/notes.md": b"\xff",
    })
    assert docscheck.check(root) == (1, [Problem("docs/notes.md", 3, "is not UTF-8 text")])


def test_link_problems_reports_a_reference_link_whose_target_is_missing(repo):
    text = "See [the map][map].\n\n[map]: gone.md\n"
    assert problems_of(repo, text) == [Problem("docs/index.md", 3, "link to gone.md, which does not exist")]


def test_link_problems_checks_a_reference_definition_like_an_inline_link(repo):
    text = (
        "[c](gone.md) and [the map][map].\n\n"
        "[map]: modules/main.md\n[part]: ../AGENTS.md#nothing\n[site]: https://example.invalid/x.md\n"
    )
    assert problems_of(repo, text) == [
        Problem("docs/index.md", 1, "link to gone.md, which does not exist"),
        Problem("docs/index.md", 4, "link to ../AGENTS.md#nothing, whose heading does not exist"),
    ]


def test_title_returns_the_first_level_one_heading_or_an_empty_string():
    assert docscheck.title("## Part\n# ADR-0001: Name\n# Second\n") == "ADR-0001: Name"
    assert docscheck.title("## Part only\n") == ""
    assert docscheck.title("Intro\n\nUnderlined name\n===\n") == "Underlined name"
