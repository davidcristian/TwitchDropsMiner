from __future__ import annotations

import asyncio

from yarl import URL

from channel import Channel
from constants import JsonType, State
from fakes import (
    CLAIMED,
    NO_CAMPAIGNS,
    TOKEN,
    USHER_LIST,
    FakeResponse,
    FakeTwitch,
    GQLAnswer,
    campaign_data,
    drop_data,
    gql_answers,
    inventory,
    stream_user,
)
from inventory import DropsCampaign
from livetwitch import run_with_fast_clock
from twitch import Twitch

SPECIAL_GAME = {"id": "509663", "name": "Special Events", "boxArtURL": "https://example.invalid/509663-285x380.jpg"}
NULL_USER = {"data": {"currentUser": None}}
CLAIM_EVENT = {"type": "drop-claim", "data": {"drop_id": "d1", "drop_instance_id": "1#c1#d1"}}


def campaign_answers(drop: JsonType, **answers: JsonType | GQLAnswer) -> GQLAnswer:
    """Return GQL answers for an inventory with one campaign of GAME and this drop, and for the other operations."""
    return gql_answers(Inventory=inventory([campaign_data([drop])]), Campaigns=NO_CAMPAIGNS, **answers)


def online_channel(twitch: Twitch) -> Channel:
    channel = Channel(twitch, id=1, login="c1")
    channel.external_update(stream_user(1, online=True), [])
    return channel


def test_a_special_game_campaign_makes_a_channel_watchable_only_while_its_game_is_wanted(live_twitch):
    twitch = live_twitch(FakeTwitch())
    campaign = DropsCampaign(twitch, campaign_data([drop_data("d1")], game=SPECIAL_GAME), {})
    twitch.inventory = [campaign]
    # the channel streams GAME, which no campaign has
    channel = online_channel(twitch)

    watchable = []
    for wanted in ([], [campaign.game]):
        twitch.wanted_games = wanted
        watchable.append(twitch.can_watch(channel))

    assert watchable == [False, True]


def test_a_drop_claim_event_for_a_claimed_drop_changes_no_state_and_sends_no_request(live_twitch):
    fake = FakeTwitch(gql=campaign_answers(drop_data("d1", watched=120, claim_id="1#c1#d1"), ClaimDrop=CLAIMED))

    async def scenario():
        twitch = live_twitch(fake)
        await twitch.fetch_inventory()
        # claimed as GAMES_UPDATE claims it, before the event arrives
        await twitch.inventory[0].timed_drops["d1"].claim()
        await twitch.process_drops(1, CLAIM_EVENT)
        return twitch._state

    assert run_with_fast_clock(scenario()) is State.IDLE
    assert fake.gql_sent == ["Inventory", "Campaigns", "ClaimDrop"]
    assert len(fake.printed) == 1


def test_a_drop_claim_event_stops_asking_for_the_current_drop_at_a_null_user(live_twitch):
    fake = FakeTwitch(gql=campaign_answers(drop_data("d1", watched=120), ClaimDrop=CLAIMED, CurrentDrop=NULL_USER))

    async def scenario():
        twitch = live_twitch(fake)
        await twitch.fetch_inventory()
        twitch.watching_channel.set(online_channel(twitch))
        await twitch.process_drops(1, CLAIM_EVENT)
        return twitch._state

    # the campaign has no other drop, so the claim reloads the inventory
    assert run_with_fast_clock(scenario()) is State.INVENTORY_FETCH
    assert fake.gql_sent == ["Inventory", "Campaigns", "ClaimDrop", "CurrentDrop"]


def test_the_watch_loop_adds_a_minute_itself_after_a_null_user_in_the_current_drop(live_twitch):
    def playlists(method: str, url: URL) -> FakeResponse:
        return FakeResponse(200, USHER_LIST if url.host == "usher.ttvnw.net" else "")

    fake = FakeTwitch(
        gql=campaign_answers(drop_data("d1"), PlaybackAccessToken=TOKEN, CurrentDrop=NULL_USER), http=playlists
    )

    async def scenario():
        twitch = live_twitch(fake)
        await twitch.fetch_inventory()
        twitch.wanted_games = [twitch.inventory[0].game]
        twitch.watching_channel.set(online_channel(twitch))
        watch_loop = asyncio.create_task(twitch._watch_loop())
        # the loop asks for the current drop 15 seconds after its watch request, and this clock skips the wait
        await asyncio.sleep(30)
        return twitch, watch_loop.done()

    twitch, ended = run_with_fast_clock(scenario())

    assert (ended, twitch._state) == (False, State.IDLE)
    assert twitch.inventory[0].timed_drops["d1"].current_minutes == 1
    assert fake.gql_sent == ["Inventory", "Campaigns", "PlaybackAccessToken", "CurrentDrop"]
