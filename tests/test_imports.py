from __future__ import annotations

import importlib

import pytest

# The modules that import the app's packages, which requirements-dev.txt installs for the tests
MODULES = ["channel", "main", "settings", "utils"]


@pytest.mark.parametrize("name", MODULES)
def test_the_module_imports(name):
    importlib.import_module(name)
