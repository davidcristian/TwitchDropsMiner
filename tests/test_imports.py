from __future__ import annotations

import importlib

import pytest

# The modules that import the app's packages, which requirements-dev.txt installs for the tests
MODULES = ["cache", "channel", "gui", "inventory", "main", "settings", "translate", "twitch", "utils", "websocket"]


@pytest.mark.parametrize("name", MODULES)
def test_the_module_imports(name):
    importlib.import_module(name)
