from __future__ import annotations

import pytest

import docscheck
from sources import Problem

NAME = "docs/index.md"
PATHS = docscheck.known_paths([NAME, "docs/logo.png", "docs/modules/main.md", "AGENTS.md"])
GONE = Problem(NAME, 1, "link to gone.md, which does not exist")


def problems_of(text: str) -> list[Problem]:
    return docscheck.link_problems(NAME, {NAME: text, "AGENTS.md": "# Rules\n"}, PATHS)


@pytest.mark.parametrize(
    "link",
    ["[a](//example.invalid/page)", "[a](//gone.md)", "[a]: //example.invalid/page", "[a](<//example.invalid/x.md>)"],
    ids=["inline", "a path after //", "definition", "angle brackets"],
)
def test_link_problems_skips_a_protocol_relative_link_as_a_url(link):
    assert problems_of(f"{link}\n") == []


def test_links_returns_a_link_with_a_title_angle_brackets_or_an_image_as_its_text():
    text = (
        "[a](x.md \"Title\") [b](y.md 'Title') [c](z.md (Title)) [d](<my file.md>) [e]( <w.md> \"T\" )\n"
        "[![badge](logo.png)](v.md) [`[f](u.md)`](t.md)\n"
    )
    assert docscheck.links(text) == [
        (1, "a", "x.md"),
        (1, "b", "y.md"),
        (1, "c", "z.md"),
        (1, "d", "my file.md"),
        (1, "e", "w.md"),
        (2, "![badge](logo.png)", "v.md"),
        (2, "badge", "logo.png"),
        (2, "`[f](u.md)`", "t.md"),
    ]


@pytest.mark.parametrize(
    "link",
    [
        '[a](gone.md "Title")',
        "[a](gone.md 'Title')",
        "[a](gone.md (Title))",
        "[![badge](logo.png)](gone.md)",
        "[a](<gone.md>)",
        '[a](<gone.md> "Title")',
    ],
    ids=["double quoted title", "single quoted title", "title in parentheses", "image as text", "angle brackets",
         "angle brackets and a title"],
)
def test_link_problems_checks_a_link_with_a_title_an_image_as_text_or_angle_brackets(link):
    assert problems_of(f"{link}\n") == [GONE]


def test_link_problems_checks_the_image_inside_a_link_and_accepts_both_when_they_exist():
    text = "[![badge](logo.png)](modules/main.md) [![badge](gone.png)](modules/main.md \"Main\")\n"
    assert problems_of(text) == [Problem(NAME, 1, "link to gone.png, which does not exist")]


@pytest.mark.parametrize(
    "before",
    ["---", "***", "Title\n===", "Part\n---", "<!-- a note -->", "Text that ends", "## Heading", "| a | b |"],
    ids=["break", "star break", "equals underline", "dash underline", "comment", "paragraph", "heading", "table row"],
)
def test_definitions_reads_a_definition_whatever_line_comes_before_it(before):
    text = f"{before}\n[map]: gone.md\n"
    number = before.count("\n") + 2
    assert docscheck.definitions(text) == [(number, "gone.md")]
    assert problems_of(text) == [Problem(NAME, number, "link to gone.md, which does not exist")]
