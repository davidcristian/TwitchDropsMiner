from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from channel import Channel
from constants import JsonType
from fakes import GAME, FakeTwitch, campaign_data, drop_data, stream_user
from inventory import DropsCampaign
from twitch import Twitch

SECRET = "s3cret-token"
GOOD_JAR = json.dumps({"twitch.tv|": {"auth-token": {
    "key": "auth-token", "value": SECRET, "coded_value": SECRET, "path": "/", "domain": "twitch.tv",
}}})


def test_the_bulk_check_clears_the_stream_of_an_offline_channel_and_keeps_that_of_a_missing_one():
    users: dict[str, JsonType | None] = {}
    twitch = FakeTwitch(gql=lambda op: {"data": {"user": users[op["variables"]["channel"]]}})
    channels = [Channel(twitch, id=number, login=f"c{number}", acl_based=True) for number in (1, 2, 3)]

    users.update(c1=stream_user(1, online=True), c2=stream_user(2, online=True), c3=stream_user(3, online=False))
    asyncio.run(Twitch.bulk_check_online(twitch, channels))
    first_pass = [channel.online for channel in channels]
    # A server error sets the user to null
    users.update(c1=stream_user(1, online=False), c2=None, c3=stream_user(3, online=True))
    asyncio.run(Twitch.bulk_check_online(twitch, channels))

    assert first_pass == [True, True, False]
    assert [channel.online for channel in channels] == [False, True, True]
    assert twitch.gql_sent == ["GetStreamInfo"] * 6


async def session_cookies(twitch: Twitch) -> int:
    """Return the number of cookies in a new session of twitch, and close the session."""
    # the live_twitch fixture gives twitch a fake session, and get_session creates one only when there is none
    twitch._session = None
    session = await twitch.get_session()
    cookies = len(session.cookie_jar)
    await session.close()
    return cookies


@pytest.mark.parametrize("contents", [
    "",
    GOOD_JAR[:GOOD_JAR.index(SECRET) + len(SECRET) + 2],
    "[1, 2]",
    None,
], ids=["empty", "cut off after the token", "JSON list", "folder"])
def test_a_cookies_jar_that_fails_to_load_logs_one_warning_and_leaves_no_cookie(live_twitch, tmp_path, caplog,
                                                                                contents):
    if contents is None:
        (tmp_path / "cookies.jar").mkdir()
    else:
        (tmp_path / "cookies.jar").write_text(contents, encoding="utf-8")

    assert asyncio.run(session_cookies(live_twitch(FakeTwitch()))) == 0
    warnings = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith("Could not load cookies.jar, so the app logs in again (")
    assert SECRET not in caplog.text


def test_a_cookies_jar_that_loads_logs_no_warning(live_twitch, tmp_path, caplog):
    (tmp_path / "cookies.jar").write_text(GOOD_JAR, encoding="utf-8")

    assert asyncio.run(session_cookies(live_twitch(FakeTwitch()))) == 1
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


@pytest.mark.usefixtures("launcher_folders")
def test_a_folder_removed_during_a_scan_has_no_detected_games(live_twitch, tmp_path, steam_manifest):
    steam_manifest(tmp_path / "kept" / "steamapps", 10, "Solitaire")
    steam_manifest(tmp_path / "removed" / "steamapps", 20, GAME["name"])
    fake = FakeTwitch()
    fake.settings.game_dirs = [str(tmp_path / "kept"), str(tmp_path / "removed")]

    async def scenario():
        twitch = live_twitch(fake)
        twitch.inventory = [DropsCampaign(twitch, campaign_data([drop_data("d1")]), {})]
        scans = ThreadPoolExecutor(max_workers=1)
        asyncio.get_running_loop().set_default_executor(scans)
        first_scan = asyncio.create_task(twitch.detect_games())
        await asyncio.sleep(0)
        # returns once the only thread has scanned both folders, while first_scan waits for its result
        scans.submit(lambda: None).result()
        # what the Remove button does: it changes the list and asks for a scan
        del fake.settings.game_dirs[1]
        await twitch.detect_games()
        await first_scan

    asyncio.run(scenario())

    assert fake.settings.detected_games == []
