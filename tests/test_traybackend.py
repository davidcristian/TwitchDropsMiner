from __future__ import annotations

import logging
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from traybackend import (
    BACKEND_VARIABLE, BUTTON_PRESS_MASK, XORG_MODULE, icon_class, import_pystray, load_pystray, session_bus_error
)

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


class FakeBus:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls = 0

    def __call__(self) -> str | None:
        self.calls += 1
        return self.error


@pytest.fixture(autouse=True)
def warnings_captured(caplog):
    caplog.set_level(logging.WARNING, logger="TwitchDrops")


def load(platform, environ, bus=None, **errors):
    fake = FakeLoad(environ, errors)
    return import_pystray(fake, environ, platform, bus or FakeBus()), fake.backends


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
        import_pystray(fake, environ, "linux", FakeBus())
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
    bus = FakeBus("no bus")
    with pytest.raises(AssertionError):
        import_pystray(fake, environ, "linux", bus)
    assert fake.backends == ["gtk"]
    assert bus.calls == 0
    assert environ == {BACKEND_VARIABLE: "gtk"}
    assert warnings(caplog) == []


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_windows_and_macos_import_pystray_alone_with_its_own_choice(platform):
    environ: dict[str, str] = {}
    bus = FakeBus("no bus")
    assert load(platform, environ, bus) == (PYSTRAY, [None])
    fake = FakeLoad(environ, {None: ValueError("broken")})
    with pytest.raises(ValueError, match="broken"):
        import_pystray(fake, environ, platform, bus)
    assert fake.backends == [None]
    assert bus.calls == 0
    assert environ == {}


def test_without_a_session_bus_the_xorg_backend_is_imported_alone(caplog):
    environ: dict[str, str] = {}
    bus = FakeBus("Could not connect: No such file or directory")
    assert load("linux", environ, bus) == (PYSTRAY, ["xorg"])
    assert bus.calls == 1
    assert environ == {}
    assert warnings(caplog) == [
        "Tray icon: the app cannot connect to the DBus session bus (Could not connect: No such file or directory), "
        "which the appindicator and gtk backends need, so it uses the xorg backend"
    ]


def test_without_a_session_bus_an_error_of_the_xorg_backend_stops_the_import():
    environ = {BACKEND_VARIABLE: ""}
    error = ImportError("No module named 'Xlib'")
    with pytest.raises(ImportError) as raised:
        load("linux", environ, FakeBus("no bus"), xorg=error)
    assert raised.value is error
    assert environ == {BACKEND_VARIABLE: ""}


def test_the_session_bus_check_returns_none_without_pygobject(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)
    assert session_bus_error() is None


def test_the_session_bus_check_returns_the_error_of_an_address_with_no_bus(monkeypatch, tmp_path):
    gi = pytest.importorskip("gi")
    try:
        gi.require_version("Gio", "2.0")
    except ValueError:
        pytest.skip("the Gio typelib is not installed")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", f"unix:path={tmp_path / 'bus'}")
    assert session_bus_error() == "Could not connect: No such file or directory"


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


# ExposureMask and StructureNotifyMask, which pystray 0.19.5 selects on its xorg icon window
XORG_EVENTS = (1 << 15) | (1 << 17)


class FakeWindow:
    def __init__(self) -> None:
        self.mask = XORG_EVENTS

    def get_attributes(self) -> SimpleNamespace:
        return SimpleNamespace(your_event_mask=self.mask)

    def change_attributes(self, *, event_mask: int) -> None:
        self.mask = event_mask


class FakeXorgIcon:
    def __init__(self) -> None:
        self.window = self._create_window()

    def _create_window(self) -> FakeWindow:
        return FakeWindow()


FakeXorgIcon.__module__ = XORG_MODULE


def test_the_xorg_icon_window_selects_button_press_and_keeps_the_events_pystray_selects():
    icon = icon_class(FakeXorgIcon)()
    assert isinstance(icon, FakeXorgIcon)
    assert icon.window.mask == XORG_EVENTS | BUTTON_PRESS_MASK


@pytest.mark.parametrize("module", ["pystray._appindicator", "pystray._gtk", "pystray._dummy", "pystray._win32"])
def test_the_icon_class_of_another_backend_is_returned_unchanged(module):
    icon = type("Icon", (), {"__module__": module})
    assert icon_class(icon) is icon


def next_event(connection, kind: int):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        while connection.pending_events():
            if (event := connection.next_event()).type == kind:
                return event
        time.sleep(0.01)
    pytest.fail(f"no X event of type {kind} within 10 seconds")


def test_a_left_click_on_the_docked_xorg_icon_runs_the_default_menu_item_and_a_right_click_nothing(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray._xorg
    from PIL import Image
    from Xlib import X, display as xdisplay
    from Xlib.protocol import event

    # The test owns the system tray selection, as a tray does, so pystray sends it the dock request of the icon.
    connection = xdisplay.Display()
    root = connection.screen().root
    tray = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    tray.set_selection_owner(
        connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"), X.CurrentTime
    )
    connection.flush()
    clicks: list[str] = []
    shown = threading.Event()

    def show() -> None:
        clicks.append("show")
        shown.set()

    menu = pystray.Menu(pystray.MenuItem("Show", show, default=True))
    icon = icon_class(pystray._xorg.Icon)("click_test", Image.new("RGB", (24, 24)), "Click test", menu)
    thread = threading.Thread(target=icon.run)
    thread.start()
    try:
        window = connection.create_resource_object("window", next_event(connection, X.ClientMessage).data[1][2])
        for button in (3, 1):
            press = event.ButtonPress(
                time=X.CurrentTime, root=root, window=window, child=X.NONE, root_x=0, root_y=0, event_x=0,
                event_y=0, state=0, same_screen=1, detail=button,
            )
            window.send_event(press, event_mask=X.ButtonPressMask)
        connection.flush()
        assert shown.wait(5)
        assert clicks == ["show"]
    finally:
        icon.stop()
        thread.join(5)
        tray.destroy()
        connection.close()
