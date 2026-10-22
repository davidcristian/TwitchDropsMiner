"""Read GQL response data, in which a server error leaves the field it names null."""
from __future__ import annotations

import logging
from itertools import chain
from typing import Any, TYPE_CHECKING

from exceptions import GQLException, MinerException

if TYPE_CHECKING:
    from constants import JsonType


logger = logging.getLogger("TwitchDrops")
# DropsCampaign reads these objects, and null details or a server error can leave a campaign without one
CAMPAIGN_FIELDS = ("game", "self", "allow", "timeBasedDrops")
# DropsCampaign and BaseDrop read these times, and a merge fills a null one from another response when it can
TIME_FIELDS = ("startAt", "endAt")
# Game and DropsCampaign read these fields of a campaign's game, and Game reads displayName before name
GAME_FIELDS = ("id", "boxArtURL")
CLAIMED_STATUSES = ("ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED")


def _is_index(value: Any, key: str | int) -> bool:
    """Return True when value is a list and key is the index of one of its items."""
    return isinstance(value, list) and isinstance(key, int) and 0 <= key < len(value)


def get_field(data: Any, *path: str | int) -> Any:
    """Return the value at path in GQL data, or None when a field on the way is null or missing."""
    for key in path:
        if isinstance(data, dict):
            data = data.get(key)
        elif _is_index(data, key):
            data = data[key]
        else:
            return None
    return data


def clear_error_field(data: Any, path: list[str | int]) -> bool:
    """Set the field at a server error's path to None, and return False when the path names no field."""
    if not path:
        return False
    parent = get_field(data, *path[:-1])
    if isinstance(parent, dict) or _is_index(parent, path[-1]):
        parent[path[-1]] = None
        return True
    return False


def merge_data(primary: JsonType, secondary: JsonType) -> JsonType:
    """Merge two dicts at every depth, keeping primary's value where both have one; None counts as no value."""
    merged: JsonType = {}
    for key in set(chain(primary.keys(), secondary.keys())):
        vp = primary.get(key)
        vs = secondary.get(key)
        if vp is None or vs is None:
            merged[key] = vs if vp is None else vp
        elif not isinstance(vp, type(vs)) or not isinstance(vs, type(vp)):
            raise MinerException("Inconsistent merge data")
        elif isinstance(vp, dict):
            merged[key] = merge_data(vp, vs)
        else:
            merged[key] = vp
    return merged


def user_inventory(response: JsonType) -> JsonType:
    """Return the inventory of an Inventory response, without a null campaign in progress or a null ID."""
    inventory = get_field(response, "data", "currentUser", "inventory")
    claimed = get_field(inventory, "gameEventDrops")
    if not isinstance(claimed, list) or any(get_field(item, "lastAwardedAt") is None for item in claimed):
        # BaseDrop finds a drop without self data claimed only through the benefits in this list and their times
        raise GQLException("The Inventory response has a null inventory, claimed drop or award time")
    in_progress = [c for c in get_field(inventory, "dropCampaignsInProgress") or [] if c is not None]
    campaigns = [campaign for campaign in in_progress if campaign.get("id") is not None]
    if len(campaigns) < len(in_progress):
        logger.warning("Skipped a campaign in progress with a null ID in the Inventory response")
    benefits = [item for item in claimed if item.get("id") is not None]
    if len(benefits) < len(claimed):
        logger.warning("Skipped a claimed benefit with a null ID in the Inventory response")
    return {**inventory, "dropCampaignsInProgress": campaigns, "gameEventDrops": benefits}


def campaign_summaries(response: JsonType) -> dict[str, JsonType]:
    """Return the active and upcoming campaigns of a Campaigns response by ID, leaving out a null one."""
    user = get_field(response, "data", "currentUser")
    if user is None:
        raise GQLException("The Campaigns response has a null user")
    summaries = [campaign for campaign in get_field(user, "dropCampaigns") or [] if campaign is not None]
    readable = [summary for summary in summaries if None not in (summary.get("id"), summary.get("status"))]
    if len(readable) < len(summaries):
        logger.warning("Skipped a campaign with a null ID or status in the Campaigns response")
    return {summary["id"]: summary for summary in readable if summary["status"] in ("ACTIVE", "UPCOMING")}


def campaign_details(campaign_ids: list[str], responses: list[JsonType]) -> dict[str, JsonType]:
    """Return the campaign of each CampaignDetails response by the ID it was requested with, leaving out a null one.

    responses holds one response for each ID in campaign_ids, in the same order.
    """
    details: dict[str, JsonType] = {}
    for campaign_id, response in zip(campaign_ids, responses):
        campaign = get_field(response, "data", "user", "dropCampaign")
        if campaign is not None:
            details[campaign_id] = campaign
    return details


def _has_null_time(data: JsonType) -> bool:
    """Return True when a start or end time of a campaign or drop is null or missing."""
    return any(data.get(field) is None for field in TIME_FIELDS)


def _named(edge: JsonType) -> JsonType:
    """Return a benefit edge whose null benefit name is read as an empty name, which rewards_text can join."""
    benefit = edge["benefit"]
    return edge if benefit.get("name") is not None else {**edge, "benefit": {**benefit, "name": ""}}


def _readable_drops(campaign_id: str, drops: list[JsonType | None]) -> list[JsonType]:
    """Return the drops without a null drop, ID, time, benefit or precondition, and with an unreadable self left out."""
    readable: dict[str, JsonType] = {}
    for drop in drops:
        if drop is None:
            logger.warning(f"Skipped a null drop of campaign {campaign_id}")
            continue
        if drop.get("id") is None:
            logger.warning(f"Skipped a drop with a null ID of campaign {campaign_id}")
            continue
        if _has_null_time(drop):
            logger.warning(f"Skipped drop {drop['id']} of campaign {campaign_id}, which has a null start or end time")
            continue
        if drop.get("requiredMinutesWatched") is None:
            logger.warning(f"Skipped drop {drop['id']} of campaign {campaign_id}, which has null required minutes")
            continue
        if any(get_field(pre, "id") is None for pre in drop.get("preconditionDrops") or []):
            logger.warning(f"Skipped drop {drop['id']} of campaign {campaign_id}, which has a null precondition")
            continue
        edges = drop.get("benefitEdges") or []
        benefit_edges = [_named(edge) for edge in edges if get_field(edge, "benefit") is not None]
        # BaseDrop reads isClaimed of a self, and without a self it finds the claim through gameEventDrops
        drop = {key: value for key, value in drop.items() if key != "self" or get_field(value, "isClaimed") is not None}
        if len(benefit_edges) < len(edges):
            logger.warning(f"Skipped a null benefit of drop {drop['id']} in campaign {campaign_id}")
        if benefit_edges != edges:
            drop["benefitEdges"] = benefit_edges
        readable[drop["id"]] = drop
    # TimedDrop looks up each precondition in its campaign, so a drop whose precondition was skipped goes too
    while missing := [
        drop_id
        for drop_id, drop in readable.items()
        if any(pre["id"] not in readable for pre in drop.get("preconditionDrops") or [])
    ]:
        for drop_id in missing:
            logger.warning(f"Skipped drop {drop_id} of campaign {campaign_id}, whose precondition was skipped")
            del readable[drop_id]
    return list(readable.values())


def _readable_acl(campaign_id: str, allow: JsonType) -> JsonType | None:
    """Return the ACL without a null channel or one with a null ID or name, or None when an enabled one keeps none."""
    # DropsCampaign reads a missing isEnabled as an enabled ACL, and a null one as a disabled ACL
    allow = {key: value for key, value in allow.items() if key != "isEnabled" or value is not None}
    channels = allow.get("channels") or []
    readable = [
        channel for channel in channels
        if get_field(channel, "id") is not None and get_field(channel, "name") is not None
    ]
    if len(readable) == len(channels):
        return allow
    logger.warning(
        f"Skipped {len(channels) - len(readable)} ACL channels of campaign {campaign_id}, which are null"
        " or have a null ID or name"
    )
    if not readable and allow.get("isEnabled", True):
        # an empty list reads as no ACL, which would let every channel of the game pass the ACL check
        logger.warning(f"Skipped campaign {campaign_id}, whose ACL has no readable channel")
        return None
    return {**allow, "channels": readable}


def _readable_game(campaign_id: str, game: JsonType) -> JsonType | None:
    """Return the game without a null slug, or None when its ID, name or box art is null or missing."""
    if any(game.get(field) is None for field in GAME_FIELDS) or (game.get("displayName") or game.get("name")) is None:
        logger.warning(f"Skipped campaign {campaign_id}, whose game has a null ID, name or box art")
        return None
    # Game forms a missing slug from the name, and GameDirectory looks up the game's streams by that slug
    return {key: value for key, value in game.items() if key != "slug" or value is not None}


def complete_campaigns(campaigns: dict[str, JsonType]) -> dict[str, JsonType]:
    """Return the campaigns that DropsCampaign can read, each with its readable game, drops and ACL channels."""
    complete: dict[str, JsonType] = {}
    for campaign_id, campaign in campaigns.items():
        if any(campaign.get(field) is None for field in CAMPAIGN_FIELDS):
            # not logged: a campaign whose details are null has only its summary, which lacks some of these
            continue
        if _has_null_time(campaign):
            logger.warning(f"Skipped campaign {campaign_id}, which has a null start or end time")
            continue
        if campaign["self"].get("isAccountConnected") is None:
            logger.warning(f"Read campaign {campaign_id} as not linked, because its account connection is null")
            campaign = {**campaign, "self": {**campaign["self"], "isAccountConnected": False}}
        game = _readable_game(campaign_id, campaign["game"])
        if game is None:
            continue
        allow = _readable_acl(campaign_id, campaign["allow"])
        if allow is not None:
            drops = _readable_drops(campaign_id, campaign["timeBasedDrops"])
            complete[campaign_id] = {**campaign, "game": game, "allow": allow, "timeBasedDrops": drops}
    return complete


def current_drop(response: JsonType) -> JsonType | None:
    """Return the drop session of a CurrentDrop response, or None when it or the user is null."""
    return get_field(response, "data", "currentUser", "dropCurrentSession")


def claim_succeeded(response: JsonType) -> bool:
    """Return True when a ClaimDrop response reports the drop claimed, and False when its data is null."""
    data = get_field(response, "data")
    if not isinstance(data, dict) or data.get("errors"):
        return False
    return get_field(data, "claimDropRewards", "status") in CLAIMED_STATUSES
