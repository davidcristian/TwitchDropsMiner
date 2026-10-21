from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
from yarl import URL

import constants
from constants import ClientInfo, GQLPersistedQuery, GQLQuery, WebsocketTopic

HASH = "0123abcd"


def template(variables=None) -> GQLPersistedQuery:
    return GQLPersistedQuery("Operation", HASH, variables=variables)


def load_constants(
    argv0: Path,
    appimage: Path | None = None,
    platform: str = "linux",
    appdir: Path | str | None = None,
    source: Path | None = None,
) -> ModuleType:
    # A second copy of the module runs its import time code with test inputs. A reload of `constants` would
    # replace the classes that other modules and tests already hold.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", [str(argv0)])
        patch.setattr(sys, "platform", platform)
        patch.delattr(sys, "_MEIPASS", raising=False)
        for name, value in (("APPIMAGE", appimage), ("APPDIR", appdir)):
            if value is None:
                patch.delenv(name, raising=False)
            else:
                patch.setenv(name, str(value))
        spec = importlib.util.spec_from_file_location("constants_copy", source or constants.__file__)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def mounted_appimage(tmp_path: Path) -> tuple[Path, Path]:
    appimage = tmp_path / "apps" / "TwitchDropsMiner.AppImage"
    appimage.parent.mkdir()
    appimage.touch()
    src = tmp_path / "mount" / "usr" / "src"
    src.mkdir(parents=True)
    shutil.copy(constants.__file__, src / "constants.py")
    return appimage, src


def received_by(log: list):
    def process(target_id, message):
        log.append((target_id, message))
        return "handled"

    return process


def test_persisted_query_holds_the_name_and_hash_and_no_query_text():
    assert template() == {
        "operationName": "Operation",
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH}},
    }


def test_with_variables_fills_a_required_variable_and_keeps_the_defaults():
    query = template({"channel": ..., "limit": 30}).with_variables({"channel": "streamer"})
    assert isinstance(query, GQLPersistedQuery)
    assert query == {
        "operationName": "Operation",
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH}},
        "variables": {"channel": "streamer", "limit": 30},
    }


def test_with_variables_overwrites_a_default_and_adds_a_variable_the_template_lacks():
    query = template({"limit": 30}).with_variables({"limit": 10, "cursor": "abc"})
    assert query["variables"] == {"limit": 10, "cursor": "abc"}


def test_with_variables_on_a_query_without_variables_uses_the_given_ones():
    base = template()
    assert base.with_variables({"limit": 10})["variables"] == {"limit": 10}
    assert "variables" not in base


def test_with_variables_merges_a_nested_dict_into_the_template():
    base = template({"slug": ..., "options": {"sort": "RELEVANCE", "systemFilters": []}})
    query = base.with_variables({"slug": "game", "options": {"systemFilters": ["DROPS_ENABLED"]}})
    assert query["variables"] == {
        "slug": "game",
        "options": {"sort": "RELEVANCE", "systemFilters": ["DROPS_ENABLED"]},
    }


def test_with_variables_replaces_an_unset_value_with_a_dict():
    query = template({"input": ...}).with_variables({"input": {"id": "n1"}})
    assert query["variables"] == {"input": {"id": "n1"}}


def test_with_variables_leaves_the_template_unchanged():
    base = template({"channel": ..., "options": {"sort": "RELEVANCE"}})
    base.with_variables({"channel": "streamer", "options": {"sort": "VIEWER_COUNT"}})
    assert base["variables"] == {"channel": ..., "options": {"sort": "RELEVANCE"}}


@pytest.mark.parametrize("variables", [{}, {"limit": 10}, {"channel": ...}])
def test_with_variables_raises_when_a_required_variable_is_unset(variables):
    with pytest.raises(RuntimeError, match="^Unspecified variable: 'channel'$"):
        template({"channel": ..., "limit": 30}).with_variables(variables)


def test_with_variables_raises_for_an_unset_nested_variable_and_keeps_the_template():
    base = template({"input": {"claimID": ..., "channelID": ...}})
    with pytest.raises(RuntimeError, match="^Unspecified variable: 'channelID'$"):
        base.with_variables({"input": {"claimID": "c1"}})
    assert base["variables"] == {"input": {"claimID": ..., "channelID": ...}}


def test_with_variables_keeps_an_unset_value_inside_a_dict_the_caller_leaves_out():
    query = template({"input": {"dropInstanceID": ...}}).with_variables({})
    assert query["variables"] == {"input": {"dropInstanceID": ...}}


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"input": "n1"}, "Base is a dict, var is not: 'input'"),
        ({"limit": {"value": 10}}, "Var is a dict, base is not: 'limit'"),
    ],
)
def test_with_variables_raises_when_a_dict_meets_a_value_that_is_not_a_dict(variables, message):
    with pytest.raises(RuntimeError, match=f"^{message}$"):
        template({"input": {"id": ""}, "limit": 30}).with_variables(variables)


def test_gql_query_sends_the_query_text_with_the_encoded_data():
    assert GQLQuery("mutation SendEvents {}", "H4sIAAAA") == {
        "query": "mutation SendEvents {}",
        "variables": {"input": {"data": "H4sIAAAA", "repository": "twilight", "encoding": "GZIP_B64"}},
    }


def test_client_info_with_one_user_agent_uses_it():
    info = ClientInfo(URL("https://www.twitch.tv"), "client-id", "Agent/1.0")
    assert tuple(info) == (URL("https://www.twitch.tv"), "client-id", "Agent/1.0")


def test_client_info_with_a_list_picks_one_user_agent_from_it():
    agents = ["Agent/1.0", "Agent/2.0", "Agent/3.0"]
    assert ClientInfo(URL("https://m.twitch.tv"), "client-id", agents).USER_AGENT in agents


def test_websocket_topic_text_is_the_twitch_topic_and_the_target_id():
    topic = WebsocketTopic("Channel", "StreamState", 123, received_by([]))
    assert str(topic) == "video-playback-by-id.123"
    assert repr(topic) == "Topic(video-playback-by-id.123)"
    assert WebsocketTopic.as_str("User", "Drops", 45) == "user-drop-events.45"


@pytest.mark.parametrize(("category", "name"), [("User", "StreamState"), ("Stream", "Drops")])
def test_websocket_topic_raises_for_an_unknown_topic(category, name):
    with pytest.raises(KeyError):
        WebsocketTopic.as_str(category, name, 45)


def test_websocket_topic_raises_for_a_target_id_that_is_not_an_int():
    with pytest.raises(AssertionError):
        WebsocketTopic("User", "Drops", "45", received_by([]))


def test_calling_a_websocket_topic_passes_the_target_id_and_message_to_its_process():
    log: list = []
    topic = WebsocketTopic("User", "Drops", 45, received_by(log))
    assert topic({"type": "drop-progress"}) == "handled"
    assert log == [(45, {"type": "drop-progress"})]


def test_websocket_topics_with_the_same_text_are_equal_and_count_once_in_a_set():
    first = WebsocketTopic("Channel", "StreamUpdate", 7, received_by([]))
    second = WebsocketTopic("Channel", "StreamUpdate", 7, received_by([]))
    other = WebsocketTopic("Channel", "StreamState", 7, received_by([]))
    assert first == second
    assert first != other
    assert len({first, second, other}) == 2


def test_a_websocket_topic_equals_its_text_and_no_other_type():
    topic = WebsocketTopic("Channel", "StreamUpdate", 7, received_by([]))
    assert topic == "broadcast-settings-update.7"
    assert topic != "broadcast-settings-update.8"
    assert topic != 7


def test_a_websocket_topic_is_found_in_a_set_by_its_text():
    assert "broadcast-settings-update.7" in {WebsocketTopic("Channel", "StreamUpdate", 7, received_by([]))}


def test_resource_path_from_source_is_under_the_working_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", False)
    monkeypatch.setattr(constants, "IS_PACKAGED", False)
    monkeypatch.setattr(constants, "WORKING_DIR", tmp_path)
    assert constants._resource_path("lang") == tmp_path / "lang"
    assert constants._resource_path(Path("icons", "pickaxe.ico")) == tmp_path / "icons" / "pickaxe.ico"


def test_resource_path_in_a_pyinstaller_build_is_under_the_unpack_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", False)
    monkeypatch.setattr(constants, "IS_PACKAGED", True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI1234"), raising=False)
    assert constants._resource_path("lang") == tmp_path / "_MEI1234" / "lang"


def test_resource_path_in_an_appimage_is_next_to_the_started_script(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "IS_APPIMAGE", True)
    monkeypatch.setattr(constants, "IS_PACKAGED", True)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "usr" / "src" / "main.py")])
    assert constants._resource_path("lang") == tmp_path / "usr" / "src" / "lang"


@pytest.mark.parametrize("started", ["main.py", "TwitchDropsMiner.exe", "TwitchDropsMiner"])
def test_the_app_keeps_its_files_in_the_folder_of_the_started_file(tmp_path, started):
    copy = load_constants(tmp_path / "app" / started)
    assert copy.SELF_PATH == tmp_path / "app" / started
    assert copy.WORKING_DIR == tmp_path / "app"
    assert copy.SETTINGS_PATH == tmp_path / "app" / "settings.json"
    assert copy.COOKIES_PATH == tmp_path / "app" / "cookies.jar"
    assert copy.CACHE_DB == tmp_path / "app" / "cache" / "mapping.json"
    assert copy.LANG_PATH == tmp_path / "app" / "lang"
    assert not copy.IS_PACKAGED


@pytest.mark.parametrize("started", ["gui.py", "pyinstaller"])
def test_the_gui_preview_and_pyinstaller_use_main_py_next_to_constants(tmp_path, started):
    copy = load_constants(tmp_path / "bin" / started)
    repo = Path(constants.__file__).resolve().parent
    assert copy.SELF_PATH == repo / "main.py"
    assert copy.WORKING_DIR == repo


def test_an_appimage_keeps_its_files_next_to_the_appimage_file(tmp_path):
    appimage, src = mounted_appimage(tmp_path)
    copy = load_constants(src / "main.py", appimage, appdir=tmp_path / "mount", source=src / "constants.py")
    assert copy.IS_APPIMAGE and copy.IS_PACKAGED
    assert copy.SELF_PATH == appimage
    assert copy.WORKING_DIR == tmp_path / "apps"
    assert copy.COOKIES_PATH == tmp_path / "apps" / "cookies.jar"
    assert copy.LANG_PATH == src / "lang"


@pytest.mark.parametrize("through_link", ["appdir", "module"])
def test_an_appimage_reached_through_a_symlink_keeps_its_files_next_to_the_appimage_file(tmp_path, through_link):
    appimage, src = mounted_appimage(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "mount", target_is_directory=True)
    appdir, source = (link, src) if through_link == "appdir" else (tmp_path / "mount", link / "usr" / "src")
    copy = load_constants(source / "main.py", appimage, appdir=appdir, source=source / "constants.py")
    assert copy.IS_APPIMAGE and copy.IS_PACKAGED
    assert copy.WORKING_DIR == tmp_path / "apps"


def test_an_appimage_variable_naming_a_missing_file_is_ignored(tmp_path):
    _, src = mounted_appimage(tmp_path)
    copy = load_constants(
        src / "main.py", tmp_path / "gone.AppImage", appdir=tmp_path / "mount", source=src / "constants.py"
    )
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.WORKING_DIR == src


def test_a_run_from_source_started_from_another_appimage_keeps_its_files_in_the_repo(tmp_path):
    other = tmp_path / "apps" / "Editor.AppImage"
    other.parent.mkdir()
    other.touch()
    # the AppImage runtime sets APPDIR to the mounted image, and the editor's terminal passes both on
    copy = load_constants(tmp_path / "repo" / "main.py", other, appdir=tmp_path / "mount_editor")
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.COOKIES_PATH == tmp_path / "repo" / "cookies.jar"


@pytest.mark.parametrize("appdir", [None, ""])
def test_an_appimage_variable_without_appdir_counts_as_a_run_from_source(tmp_path, monkeypatch, appdir):
    appimage, src = mounted_appimage(tmp_path)
    monkeypatch.chdir(src)
    copy = load_constants(src / "main.py", appimage, appdir=appdir, source=src / "constants.py")
    assert not copy.IS_APPIMAGE and not copy.IS_PACKAGED
    assert copy.COOKIES_PATH == src / "cookies.jar"


@pytest.mark.parametrize(("platform", "scripts"), [("win32", "Scripts"), ("linux", "bin"), ("darwin", "bin")])
def test_the_venv_scripts_folder_follows_the_platform(tmp_path, platform, scripts):
    copy = load_constants(tmp_path / "main.py", platform=platform)
    assert copy.SCRIPTS_PATH == tmp_path / "env" / scripts
