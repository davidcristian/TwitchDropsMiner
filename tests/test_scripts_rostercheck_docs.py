from __future__ import annotations

import pytest

import rostercheck
from test_scripts_rostercheck import problems_with


@pytest.mark.parametrize(
    ("changes", "problems"),
    [
        (
            {"docs/modules/gone.md": ""},
            ["docs/modules/:1: docs/modules/ has gone.md, which matches no entry of the module map"],
        ),
        (
            {"docs/modules/version.md": ""},
            ["docs/modules/:1: docs/modules/ has version.md, but version.py is documented in constants.md"],
        ),
        (
            {"version.py": None, "docs/modules/version.md": ""},
            [
                "AGENTS.md:1: the module map lists version.py, which does not exist",
                "docs/modules/:1: docs/modules/ has version.md, which matches no entry of the module map",
            ],
        ),
    ],
    ids=["a module that does not exist", "a module documented in another doc", "that module once it is gone"],
)
def test_check_reports_a_doc_that_no_module_should_have_with_the_reason(tmp_path, changes, problems):
    assert problems_with(tmp_path, changes) == problems


@pytest.mark.parametrize(
    ("module", "doc"),
    [("main.py", "main.md"), ("gamelib/", "gamelib.md")],
    ids=["a module", "a package"],
)
def test_doc_of_returns_the_doc_name_of_a_module_or_a_package(module, doc):
    assert rostercheck.doc_of(module) == doc
