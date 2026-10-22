from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from constants import JsonType
from exceptions import GQLException
from fakes import END, START, FakeTwitch, gql_answers
from livetwitch import run_with_fast_clock
from nullpaths import NullPath, null_paths, path_id, with_null

IMAGE = "https://example.invalid/b.png"
GAME = {"id": "1", "slug": "game", "displayName": "Game", "name": "Game", "boxArtURL": "https://example.invalid/1.jpg"}
CHANNELS = [{"id": "11", "name": "c11", "displayName": "C11"}, {"id": "12", "name": "c12", "displayName": "C12"}]
SENT = ("Inventory", "Campaigns", "CampaignDetails")


def drop(drop_id: str, *preconditions: str, claim: bool) -> JsonType:
    """Return a drop, with the claim data that Inventory has when claim is True."""
    benefit = {"id": f"b-{drop_id}", "name": "Reward", "distributionType": "DIRECT_ENTITLEMENT", "imageAssetURL": IMAGE}
    data = {
        "id": drop_id,
        "name": "Drop",
        "startAt": START,
        "endAt": END,
        "requiredMinutesWatched": 60,
        "preconditionDrops": [{"id": pre} for pre in preconditions] or None,
        "benefitEdges": [{"benefit": benefit}],
    }
    if claim:
        data["self"] = {"dropInstanceID": f"1#c#{drop_id}", "isClaimed": False, "currentMinutesWatched": 10}
    return data


def campaign(campaign_id: str, *, claim: bool) -> JsonType:
    """Return a campaign with an ACL of two channels and two drops, the second of which needs the first."""
    first, second = f"{campaign_id}-d1", f"{campaign_id}-d2"
    return {
        "id": campaign_id,
        "name": "Campaign",
        "status": "ACTIVE",
        "startAt": START,
        "endAt": END,
        "accountLinkURL": "https://example.invalid/link",
        "game": GAME,
        "self": {"isAccountConnected": True},
        "allow": {"channels": CHANNELS, "isEnabled": True},
        "timeBasedDrops": [drop(first, claim=claim), drop(second, first, claim=claim)],
    }


# Only Inventory has c1, which is in progress. Campaigns has the summary of c3 and CampaignDetails the rest of it,
# and Inventory lists the benefit of its first drop as claimed.
C3 = campaign("c3", claim=False)
INVENTORY = {"data": {"currentUser": {"inventory": {
    "dropCampaignsInProgress": [campaign("c1", claim=True)],
    "gameEventDrops": [{"id": "b-c3-d1", "lastAwardedAt": "2026-10-20T00:00:00Z"}],
}}}}
SUMMARY_FIELDS = ("id", "name", "status", "startAt", "endAt", "accountLinkURL", "game", "self")
CAMPAIGNS = {"data": {"currentUser": {"dropCampaigns": [{key: C3[key] for key in SUMMARY_FIELDS}]}}}
DETAILS = {"data": {"user": {"id": "1", "dropCampaign": C3}}}


@dataclass(frozen=True)
class Outcome:
    """How a reload with a null value differs from the reload of the complete responses."""

    gone: tuple[str, ...] = ()
    changed: dict[str, Any] = field(default_factory=dict)
    warned: bool = False
    raises: bool = False
    sent: tuple[str, ...] = SENT


def drop_outcomes(path: NullPath, key: str, *, after: str = "", needs: bool = False, claim: bool = True,
                  claimed: bool = False) -> dict[NullPath, Outcome]:
    """Return the outcomes of a null field of the drop at path, which key names in a reload.

    after names the drop that needs it; claim says it has claim data, and claimed that Inventory claims its benefit.
    """
    gone = Outcome(gone=(key, after) if after else (key,), warned=True)
    benefit = (*path, "benefitEdges", 0, "benefit")
    reward = (f"b-{key.split('/')[1]}", "DIRECT_ENTITLEMENT", IMAGE)
    unclaimed = {f"{key}.claimed": False, f"{key}.minutes": 0} if claimed else {}
    no_benefit = {f"{key}.rewards": "", f"{key}.benefits": (), **unclaimed}
    outcomes = {
        **dict.fromkeys([path, *((*path, name) for name in ("id", "startAt", "endAt", "requiredMinutesWatched"))], gone),
        (*path, "name"): Outcome(changed={f"{key}.name": ""}),
        (*path, "benefitEdges"): Outcome(changed=no_benefit),
        (*path, "benefitEdges", 0): Outcome(changed=no_benefit, warned=True),
        benefit: Outcome(changed=no_benefit, warned=True),
        (*benefit, "id"): Outcome(changed={f"{key}.benefits": ((None, *reward[1:]),), **unclaimed}),
        (*benefit, "name"): Outcome(changed={f"{key}.rewards": ""}),
        (*benefit, "distributionType"): Outcome(changed={f"{key}.benefits": ((reward[0], "UNKNOWN", IMAGE),)}),
        (*benefit, "imageAssetURL"): Outcome(changed={f"{key}.benefits": ((*reward[:2], None),)}),
    }
    if needs:
        precondition = (*path, "preconditionDrops", 0)
        outcomes[precondition[:-1]] = Outcome(changed={f"{key}.preconditions": ()})
        outcomes[precondition] = outcomes[(*precondition, "id")] = gone
    if claim:
        no_claim = {f"{key}.claim_id": None, f"{key}.minutes": 0}
        outcomes[(*path, "self")] = outcomes[(*path, "self", "isClaimed")] = Outcome(changed=no_claim)
        outcomes[(*path, "self", "dropInstanceID")] = Outcome(changed={f"{key}.claim_id": None})
        outcomes[(*path, "self", "currentMinutesWatched")] = Outcome(changed={f"{key}.minutes": 0})
    return outcomes


def acl_outcomes(allow: NullPath, key: str) -> dict[NullPath, Outcome]:
    """Return the outcomes of a null field of the ACL at allow, of the campaign that key names."""
    outcomes = {(*allow, "channels"): Outcome(changed={f"{key}.acl": ()})}
    for index, other in ((0, ("C12",)), (1, ("C11",))):
        channel = (*allow, "channels", index)
        outcomes.update(dict.fromkeys([channel, (*channel, "id"), (*channel, "name")], Outcome(
            changed={f"{key}.acl": other}, warned=True
        )))
        login = ("c11", "C12") if index == 0 else ("C11", "c12")
        outcomes[(*channel, "displayName")] = Outcome(changed={f"{key}.acl": login})
    return outcomes


def campaign_outcomes(path: NullPath, key: str, *, claim: bool, claimed: bool) -> dict[NullPath, Outcome]:
    """Return the outcomes of a null ACL or drop field of the campaign at path, which key names."""
    drops = (*path, "timeBasedDrops")
    return {
        **dict.fromkeys([(*path, "allow"), drops], Outcome(gone=(key,))),
        **acl_outcomes((*path, "allow"), key),
        **drop_outcomes((*drops, 0), f"{key}/{key}-d1", after=f"{key}/{key}-d2", claim=claim, claimed=claimed),
        **drop_outcomes((*drops, 1), f"{key}/{key}-d2", needs=True, claim=claim),
    }


IN_PROGRESS = ("data", "currentUser", "inventory", "dropCampaignsInProgress", 0)
CLAIMED = ("data", "currentUser", "inventory", "gameEventDrops")
NULL_INVENTORY = Outcome(raises=True, sent=("Inventory",))
GONE, LEFT_OUT = Outcome(gone=("c1",)), Outcome(gone=("c1",), warned=True)
# The outcome of each null path whose reload differs from the reload of the complete responses.
INVENTORY_OUTCOMES = {
    **dict.fromkeys([IN_PROGRESS[:end] for end in range(1, 4)], NULL_INVENTORY),
    **dict.fromkeys([CLAIMED, (*CLAIMED, 0), (*CLAIMED, 0, "lastAwardedAt")], NULL_INVENTORY),
    (*CLAIMED, 0, "id"): Outcome(changed={"c3/c3-d1.claimed": False, "c3/c3-d1.minutes": 0}, warned=True),
    **dict.fromkeys([IN_PROGRESS[:-1], IN_PROGRESS, (*IN_PROGRESS, "game"), (*IN_PROGRESS, "self")], GONE),
    **dict.fromkeys([(*IN_PROGRESS, name) for name in ("id", "startAt", "endAt")], LEFT_OUT),
    **dict.fromkeys([(*IN_PROGRESS, "game", "id"), (*IN_PROGRESS, "game", "boxArtURL")], LEFT_OUT),
    (*IN_PROGRESS, "name"): Outcome(changed={"c1.name": ""}),
    (*IN_PROGRESS, "accountLinkURL"): Outcome(changed={"c1.link": None}),
    (*IN_PROGRESS, "self", "isAccountConnected"): Outcome(changed={"c1.linked": False}, warned=True),
    **campaign_outcomes(IN_PROGRESS, "c1", claim=True, claimed=False),
}
SUMMARY = ("data", "currentUser", "dropCampaigns", 0)
NOT_FETCHED = Outcome(gone=("c3",), sent=SENT[:2])
CAMPAIGNS_OUTCOMES = {
    **dict.fromkeys([SUMMARY[:1], SUMMARY[:2]], Outcome(raises=True, sent=SENT[:2])),
    **dict.fromkeys([SUMMARY[:3], SUMMARY], NOT_FETCHED),
    **dict.fromkeys([(*SUMMARY, "id"), (*SUMMARY, "status")], replace(NOT_FETCHED, warned=True)),
}
DETAILS_CAMPAIGN = ("data", "user", "dropCampaign")
# a field of the summary is read from it when the details have it null
DETAILS_OUTCOMES = {
    **dict.fromkeys([DETAILS_CAMPAIGN[:end] for end in range(1, 4)], Outcome(gone=("c3",))),
    **campaign_outcomes(DETAILS_CAMPAIGN, "c3", claim=False, claimed=True),
}


def warned(caplog: pytest.LogCaptureFixture) -> bool:
    return any(record.levelno == logging.WARNING for record in caplog.records)


def reloaded(twitch: Any) -> dict[str, Any]:
    """Return what the window and the run read of each campaign and drop after a reload, by a key that names it."""
    values: dict[str, Any] = {}
    for item in twitch.inventory:
        game = item.game
        values.update({
            f"{item.id}.name": item.name,
            f"{item.id}.linked": item.linked,
            f"{item.id}.link": item.link_url,
            f"{item.id}.active": item.active,
            f"{item.id}.game": (game.id, game.name, game.slug),
            f"{item.id}.acl": tuple(channel.name for channel in item.allowed_channels),
        })
        for timed in item.drops:
            key = f"{item.id}/{timed.id}"
            values.update({
                f"{key}.name": timed.name,
                f"{key}.claimed": timed.is_claimed,
                f"{key}.claim_id": timed.claim_id,
                f"{key}.minutes": timed.current_minutes,
                f"{key}.preconditions": tuple(timed.precondition_drops),
                f"{key}.rewards": timed.rewards_text(),
                f"{key}.benefits": tuple((b.id, b.type.name, b.image_url) for b in timed.benefits),
            })
    return values


def reload(live_twitch, responses: dict[str, JsonType]) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Return what a reload with these responses reads, or None when it raises GQLException, and the GQL sent."""
    fake = FakeTwitch(gql=gql_answers(**responses))

    async def scenario() -> dict[str, Any]:
        twitch = live_twitch(fake)
        await twitch.fetch_inventory()
        return reloaded(twitch)

    try:
        return run_with_fast_clock(scenario()), tuple(fake.gql_sent)
    except GQLException:
        return None, tuple(fake.gql_sent)


COMPLETE = {"Inventory": INVENTORY, "Campaigns": CAMPAIGNS, "CampaignDetails": DETAILS}


def check_null(live_twitch, caplog, key: str, path: NullPath, outcome: Outcome) -> None:
    complete, _sent = reload(live_twitch, COMPLETE)
    caplog.clear()

    values, sent = reload(live_twitch, {**COMPLETE, key: with_null(COMPLETE[key], path)})

    kept = {
        name: value for name, value in complete.items()
        if not any(name.startswith((f"{gone}.", f"{gone}/")) for gone in outcome.gone)
    }
    assert (values, warned(caplog), sent) == (
        None if outcome.raises else {**kept, **outcome.changed}, outcome.warned, outcome.sent
    )


@pytest.mark.parametrize("path", null_paths(INVENTORY), ids=path_id)
def test_a_null_in_the_inventory_gives_the_documented_campaigns(live_twitch, caplog, path):
    check_null(live_twitch, caplog, "Inventory", path, INVENTORY_OUTCOMES.get(path, Outcome()))


@pytest.mark.parametrize("path", null_paths(CAMPAIGNS), ids=path_id)
def test_a_null_in_the_campaign_summaries_gives_the_documented_campaigns(live_twitch, caplog, path):
    check_null(live_twitch, caplog, "Campaigns", path, CAMPAIGNS_OUTCOMES.get(path, Outcome()))


@pytest.mark.parametrize("path", null_paths(DETAILS), ids=path_id)
def test_a_null_in_the_campaign_details_gives_the_documented_campaigns(live_twitch, caplog, path):
    check_null(live_twitch, caplog, "CampaignDetails", path, DETAILS_OUTCOMES.get(path, Outcome()))


def test_the_complete_responses_give_two_linked_campaigns_with_their_drops(live_twitch):
    values, sent = reload(live_twitch, COMPLETE)

    assert (values["c1.linked"], values["c3.linked"], values["c3/c3-d1.claimed"]) == (True, True, True)
    assert sorted(name for name in values if name.endswith(".rewards")) == [
        "c1/c1-d1.rewards", "c1/c1-d2.rewards", "c3/c3-d1.rewards", "c3/c3-d2.rewards"
    ]
    assert sent == SENT


@pytest.mark.parametrize("response, outcomes", [
    (INVENTORY, INVENTORY_OUTCOMES),
    (CAMPAIGNS, CAMPAIGNS_OUTCOMES),
    (DETAILS, DETAILS_OUTCOMES),
])
def test_each_outcome_table_names_only_paths_of_its_response(response, outcomes):
    assert set(outcomes) <= set(null_paths(response))
