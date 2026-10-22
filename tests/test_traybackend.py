from __future__ import annotations

import logging
import sys
from types import ModuleType

import pytest

from traybackend import BACKEND_VARIABLE, import_pystray, load_pystray

PYSTRAY = ModuleType("pystray")


class FakeLoad:
    def __init__(self, environ: dict[str, str], errors: dict[str | None, BaseException]) -> None:
        self.environ = environ
        self.errors = errors
        self.backends: list[str | None] = []

    def __call__(self) -> ModuleType:
        backend = self.environ.get(BACKEND_VARIABLE)
        self.backends.append(backend)
        if backend in self.errors:
            raise self.errors[backend]
        return PYSTRAY


@pytest.fixture(autouse=True)
def warnings_captured(caplog):
    caplog.set_level(logging.WARNING, logger="TwitchDrops")


def load(platform, environ, **errors):
    fake = FakeLoad(environ, errors)
    return import_pystray(fake, environ, platform), fake.backends


def warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


@pytest.mark.parametrize("platform", ["linux", "freebsd14"])
def test_the_appindicator_backend_is_imported_alone_when_it_loads(platform, caplog):
    environ: dict[str, str] = {}
    assert load(platform, environ) == (PYSTRAY, ["appindicator"])
    assert environ == {}
    assert warnings(caplog) == []


def test_gtk_libraries_that_fail_to_load_leave_the_xorg_backend(caplog):
    environ: dict[str, str] = {}
    module, backends = load("linux", environ, appindicator=AssertionError(), gtk=AssertionError())
    assert (module, backends) == (PYSTRAY, ["appindicator", "gtk", "xorg"])
    assert environ == {}
    assert warnings(caplog) == [
        "Tray icon: the appindicator backend failed to load (AssertionError), so the app tries the gtk backend",
        "Tray icon: the gtk backend failed to load (AssertionError), so the app tries the xorg backend",
    ]


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (AssertionError(), "AssertionError"),
        (ValueError("Namespace DBus not available"), "ValueError: Namespace DBus not available"),
        (ImportError("Gtk could not be initialised"), "ImportError: Gtk could not be initialised"),
    ],
)
def test_a_broken_appindicator_backend_moves_on_to_the_gtk_backend(error, text, caplog):
    environ: dict[str, str] = {}
    assert load("linux", environ, appindicator=error) == (PYSTRAY, ["appindicator", "gtk"])
    assert environ == {}
    assert warnings(caplog) == [
        f"Tray icon: the appindicator backend failed to load ({text}), so the app tries the gtk backend"
    ]


def test_an_error_of_the_xorg_backend_stops_the_import():
    environ: dict[str, str] = {}
    error = ImportError("No module named 'Xlib'")
    with pytest.raises(ImportError) as raised:
        load("linux", environ, appindicator=ValueError(), gtk=ValueError(), xorg=error)
    assert raised.value is error
    assert environ == {}


def test_an_error_no_broken_backend_raises_stops_the_import(caplog):
    environ: dict[str, str] = {}
    fake = FakeLoad(environ, {"appindicator": RuntimeError("bug")})
    with pytest.raises(RuntimeError, match="bug"):
        import_pystray(fake, environ, "linux")
    assert fake.backends == ["appindicator"]
    assert environ == {}
    assert warnings(caplog) == []


def test_an_empty_variable_is_treated_as_unset_and_kept():
    environ = {BACKEND_VARIABLE: ""}
    assert load("linux", environ, appindicator=AssertionError()) == (PYSTRAY, ["appindicator", "gtk"])
    assert environ == {BACKEND_VARIABLE: ""}


def test_a_backend_the_user_chose_is_imported_alone_and_its_error_stops_the_import(caplog):
    environ = {BACKEND_VARIABLE: "gtk"}
    fake = FakeLoad(environ, {"gtk": AssertionError()})
    with pytest.raises(AssertionError):
        import_pystray(fake, environ, "linux")
    assert fake.backends == ["gtk"]
    assert environ == {BACKEND_VARIABLE: "gtk"}
    assert warnings(caplog) == []


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_windows_and_macos_import_pystray_alone_with_its_own_choice(platform):
    environ: dict[str, str] = {}
    assert load(platform, environ) == (PYSTRAY, [None])
    fake = FakeLoad(environ, {None: ValueError("broken")})
    with pytest.raises(ValueError, match="broken"):
        import_pystray(fake, environ, platform)
    assert fake.backends == [None]
    assert environ == {}


def test_load_pystray_chooses_the_backend_again_after_a_failed_import(monkeypatch):
    monkeypatch.delitem(sys.modules, "pystray", raising=False)
    monkeypatch.delitem(sys.modules, "pystray._dummy", raising=False)
    monkeypatch.setenv(BACKEND_VARIABLE, "no-such-backend")
    with pytest.raises(ImportError, match="unknown backend"):
        load_pystray()
    assert "pystray" not in sys.modules
    monkeypatch.setenv(BACKEND_VARIABLE, "dummy")
    assert load_pystray() is sys.modules["pystray"]
    assert "pystray._dummy" in sys.modules
