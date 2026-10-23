"""Fail when a list that a doc or a mock keeps no longer matches the set of things in the code it lists."""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from sources import ROOT, Problem, read_text, repo_files, write_utf8


AGENTS = "AGENTS.md"
SETTINGS_DOC = "docs/modules/settings.md"
# The GUI is gui.py and the files of ui/. The preview, which python gui.py runs, holds the settings mock.
GUI_PACKAGE = "ui/"
PREVIEW = "ui/preview.py"
MODULE_DOCS = "docs/modules/"
# Map entries that are not Python modules, and modules whose contract is in another module's doc, with that doc.
NOT_MODULES = {"docs/"}
DOCUMENTED_ELSEWHERE = {"version.py": "constants.md"}
# The scripts that are not scans: the helpers, commitlint.py, which the commit-msg hook runs, and installcheck.py,
# which the build jobs in CI run.
NOT_SCANS = {"bannedwords.py", "linerefs.py", "sources.py", "commitlint.py", "installcheck.py"}
_ROW = re.compile(r"\| `([^`]+)` \|")
_SCRIPT = re.compile(r"scripts/(\w+\.py)")


def table_names(text: str, heading: str) -> list[str]:
    """Return the backticked names in the first column of the table under a heading of a markdown text."""
    names: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.lstrip("#").strip() == heading
        elif inside and (match := _ROW.match(line)):
            names.append(match.group(1))
    return names


def compare(
    path: str, label: str, listed: list[str], actual: set[str], unknown: str = "lists {}, which does not exist"
) -> list[Problem]:
    """Return a problem for each name a list lacks, has twice, or has but the code does not.

    unknown follows the label for a listed name the code does not have, with {} in place of the name.
    """
    problems = [Problem(path, 1, f"{label} lacks {name}") for name in sorted(actual - set(listed))]
    problems.extend(Problem(path, 1, f"{label} {unknown.format(name)}") for name in sorted(set(listed) - actual))
    problems.extend(
        Problem(path, 1, f"{label} lists {name} twice") for name in sorted(set(listed)) if listed.count(name) > 1
    )
    return problems


def modules(files: list[str]) -> set[str]:
    """Return the top-level modules and packages of the app, a package written with a trailing slash."""
    top = {name for name in files if "/" not in name and name.endswith(".py")}
    return top | {name.split("/")[0] + "/" for name in files if name.count("/") == 1 and name.endswith("/__init__.py")}


def doc_of(module: str) -> str:
    """Return the file name of the doc in docs/modules/ for a module or a package."""
    return module.rstrip("/").removesuffix(".py") + ".md"


def doc_problems(files: list[str], mapped: set[str]) -> list[Problem]:
    """Return each module without a doc in docs/modules/, and each doc there that no module should have."""
    docs = [name.removeprefix(MODULE_DOCS) for name in files if name.startswith(MODULE_DOCS)]
    elsewhere = {
        doc_of(name): f"{name} is documented in {doc}" for name, doc in DOCUMENTED_ELSEWHERE.items() if name in mapped
    }
    wanted = {doc_of(name) for name in mapped - NOT_MODULES} - set(elsewhere)
    own = [name for name in docs if name not in elsewhere]
    problems = compare(MODULE_DOCS, MODULE_DOCS, own, wanted, "has {}, which matches no entry of the module map")
    extra = sorted(set(docs) & set(elsewhere))
    problems.extend(Problem(MODULE_DOCS, 1, f"{MODULE_DOCS} has {doc}, but {elsewhere[doc]}") for doc in extra)
    return problems


def class_body(module: ast.Module, name: str) -> list[ast.stmt]:
    """Return the statements of the class with this name at the top of a module, or an empty list."""
    found = (node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name)
    return next(found, ast.ClassDef(name=name, body=[])).body


def annotated(body: list[ast.stmt]) -> list[str]:
    """Return the names a class body annotates, such as the keys of a TypedDict."""
    return [node.target.id for node in body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)]


def default_keys(module: ast.Module) -> list[str]:
    """Return the keys of the default_settings dict literal."""
    for node in module.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id == "default_settings":
            if isinstance(node.value, ast.Dict):
                return [key.value for key in node.value.keys if isinstance(key, ast.Constant)]
    return []


def gui_files(files: list[str]) -> list[str]:
    """Return gui.py and the Python files of ui/, the preview always among them."""
    package = {name for name in files if name.startswith(GUI_PACKAGE) and name.endswith(".py")}
    return ["gui.py", *sorted(package | {PREVIEW})]


def mock_and_reads(gui: ast.Module, names: set[str]) -> tuple[list[str], set[str]]:
    """Return the keywords of a settings mock in a GUI file, and which of the names the file reads from settings."""
    mock: list[str] = []
    reads: set[str] = set()
    for node in ast.walk(gui):
        if isinstance(node, ast.keyword) and node.arg == "settings" and isinstance(node.value, ast.Call):
            mock = [keyword.arg for keyword in node.value.keywords if keyword.arg]
        elif isinstance(node, ast.Attribute) and node.attr in names:
            owner = node.value
            if (isinstance(owner, ast.Attribute) and owner.attr.lstrip("_") == "settings") or (
                isinstance(owner, ast.Name) and owner.id == "settings"
            ):
                reads.add(node.attr)
    return mock, reads


def settings_problems(texts: dict[str, str], gui_paths: list[str]) -> list[Problem]:
    """Return where the settings keys in settings.py, its doc and the preview mock differ.

    gui_paths lists the GUI files. The mock in PREVIEW must have every setting that one of them reads.
    """
    settings = ast.parse(texts["settings.py"])
    keys = annotated(class_body(settings, "SettingsFile"))
    actual = set(keys)
    unknown = "lists {}, which SettingsFile lacks"
    problems = compare("settings.py", "default_settings", default_keys(settings), actual, unknown)
    attributes = class_body(settings, "Settings")
    names = set(annotated(attributes)) | {node.name for node in attributes if isinstance(node, ast.FunctionDef)}
    problems.extend(Problem("settings.py", 1, f"Settings lacks the attribute {key}") for key in sorted(actual - names))
    rows = table_names(texts[SETTINGS_DOC], "The keys")
    problems.extend(compare(SETTINGS_DOC, "the key table", rows, actual, unknown))
    mock: list[str] = []
    readers: dict[str, str] = {}
    for path in gui_paths:
        found, reads = mock_and_reads(ast.parse(texts[path]), names)
        if path == PREVIEW:
            mock = found
        for name in reads:
            readers.setdefault(name, path)
    problems.extend(
        Problem(PREVIEW, 1, f"the settings mock lacks {name}, which {readers[name]} reads")
        for name in sorted(set(readers) - set(mock))
    )
    return problems


def check(root: Path) -> tuple[int, list[Problem]]:
    """Return the number of lists compared and every problem in them."""
    files = repo_files(root)
    gui_paths = gui_files(files)
    names = (AGENTS, SETTINGS_DOC, "settings.py", "justfile", *gui_paths)
    texts = {name: (read_text(root / name) or "") if (root / name).is_file() else "" for name in names}
    mapped = modules(files) | NOT_MODULES
    problems = compare(AGENTS, "the module map", table_names(texts[AGENTS], "Module map"), mapped)
    problems.extend(doc_problems(files, mapped))
    problems.extend(settings_problems(texts, gui_paths))
    scripts = {name.removeprefix("scripts/") for name in files if re.fullmatch(r"scripts/\w+\.py", name)}
    scans = scripts - NOT_SCANS
    recipes = sorted(set(_SCRIPT.findall(texts["justfile"])))
    problems.extend(compare("justfile", "the justfile", recipes, scans, "names {}, which is not a scan in scripts/"))
    section = texts[AGENTS].split("## What every change must pass", 1)[-1].split("\n## ", 1)[0]
    named = set(re.findall(r"`(\w+\.py)`", section))
    # A name such as steam.py may be a file in a package, so only a name no file in the repo has is unknown.
    file_names = {name.rsplit("/", 1)[-1] for name in files}
    listed = sorted((named & scans) | (named - file_names))
    problems.extend(compare(AGENTS, "the list of scans", listed, scans))
    return 5, sorted(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    count, problems = check(args.root)
    for problem in problems:
        print(problem)
    print(f"rostercheck: {count} lists, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    write_utf8()
    sys.exit(main())
