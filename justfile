# `just check` runs every check. The pre-commit hook and the Validate job in CI run this same recipe.

set windows-shell := ["cmd.exe", "/c"]

python := if os_family() == "windows" { "python" } else { "python3" }

# On Linux, the tests run under xvfb-run when it is installed, so the tests of the window get a virtual display.
xvfb := if os() == "linux" { `command -v xvfb-run >/dev/null && echo "xvfb-run -a" || true` } else { "" }

default: check

# Every check, in this order. The first one that fails stops the rest.
check: check-syntax check-lang check-ruff check-linecap check-dashcheck check-prosecheck check-docscheck check-rostercheck check-tests

# Every Python file parses as Python 3.10.
check-syntax:
    {{python}} scripts/syntaxcheck.py

# Every lang/*.json file is a JSON object with no key the app does not read, and its strings have no format field
# that the English string lacks. It prints how many strings each file lacks.
check-lang:
    {{python}} scripts/langcheck.py

# ruff with its default rules, set in pyproject.toml.
check-ruff:
    {{python}} -m ruff check

# At most 300 lines per Python or markdown file, except the modules linecap.py names.
check-linecap:
    {{python}} scripts/linecap.py

# No dash used as punctuation.
check-dashcheck:
    {{python}} scripts/dashcheck.py

# No banned word from the table in AGENTS.md, and no comment block or docstring over three lines.
check-prosecheck:
    {{python}} scripts/prosecheck.py

# Every link between docs resolves, no doc cites a line number, the indexes list every record, and every
# record is in its format.
check-docscheck:
    {{python}} scripts/docscheck.py

# The module map, the module docs, the settings key table and the settings mock of the preview match the code.
check-rostercheck:
    {{python}} scripts/rostercheck.py

# The test suite, with at least 80% branch coverage of the modules pyproject.toml lists.
check-tests:
    {{xvfb}} {{python}} -m pytest --cov --cov-report=term-missing:skip-covered -p no:cacheprovider
