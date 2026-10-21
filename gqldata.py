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
    """Return the inventory of an Inventory response, without a null campaign in progress."""
    inventory = get_field(response, "data", "currentUser", "inventory")
    claimed = get_field(inventory, "gameEventDrops")
    if not isinstance(claimed, list) or any(item is None for item in claimed):
        # BaseDrop finds a drop without self data claimed only through the benefits in this list
        raise GQLException("The Inventory response has a null inventory or claimed drop")
    in_progress = get_field(inventory, "dropCampaignsInProgress") or []
    return {**inventory, "dropCampaignsInProgress": [c for c in in_progress if c is not None]}


def campaign_summaries(response: JsonType) -> dict[str, JsonType]:
    """Return the active and upcoming campaigns of a Campaigns response by ID, leaving out a null one."""
    user = get_field(response, "data", "currentUser")
    if user is None:
        raise GQLException("The Campaigns response has a null user")
    return {
        campaign["id"]: campaign
        for campaign in get_field(user, "dropCampaigns") or []
        if campaign is not None and campaign["status"] in ("ACTIVE", "UPCOMING")
    }


def campaign_details(responses: list[JsonType]) -> dict[str, JsonType]:
    """Return the campaigns of CampaignDetails responses by ID, leaving out a null one."""
    details: dict[str, JsonType] = {}
    for response in responses:
        campaign = get_field(response, "data", "user", "dropCampaign")
        if campaign is not None:
            details[campaign["id"]] = campaign
    return details


def _readable_drops(campaign_id: str, drops: list[JsonType | None]) -> list[JsonType]:
    """Return the drops without a null drop, benefit or precondition, and with a null self left out."""
    readable: dict[str, JsonType] = {}
    for drop in drops:
        if drop is None:
            logger.warning(f"Skipped a null drop of campaign {campaign_id}")
            continue
        if any(pre is None for pre in drop.get("preconditionDrops") or []):
            logger.warning(f"Skipped drop {drop['id']} of campaign {campaign_id}, which has a null precondition")
            continue
        edges = drop.get("benefitEdges") or []
        benefit_edges = [edge for edge in edges if get_field(edge, "benefit") is not None]
        drop = {key: value for key, value in drop.items() if key != "self" or value is not None}
        if len(benefit_edges) < len(edges):
            logger.warning(f"Skipped a null benefit of drop {drop['id']} in campaign {campaign_id}")
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


def complete_campaigns(campaigns: dict[str, JsonType]) -> dict[str, JsonType]:
    """Return the campaigns in which none of CAMPAIGN_FIELDS is null or missing, each with its readable drops."""
    return {
        campaign_id: {**campaign, "timeBasedDrops": _readable_drops(campaign_id, campaign["timeBasedDrops"])}
        for campaign_id, campaign in campaigns.items()
        if all(campaign.get(field) is not None for field in CAMPAIGN_FIELDS)
    }


def directory_streams(response: JsonType) -> list[JsonType]:
    """Return the streams with a broadcaster in a GameDirectory response, or none when the game is null."""
    edges = get_field(response, "data", "game", "streams", "edges") or []
    return [edge["node"] for edge in edges if get_field(edge, "node", "broadcaster") is not None]


def channel_campaigns(responses: list[JsonType]) -> dict[int, list[JsonType]]:
    """Return the drop campaigns of each channel in AvailableDrops responses, leaving out a null channel."""
    campaigns: dict[int, list[JsonType]] = {}
    for response in responses:
        channel = get_field(response, "data", "channel")
        if channel is not None:
            campaigns[int(channel["id"])] = channel["viewerDropCampaigns"] or []
    return campaigns


def current_drop(response: JsonType) -> JsonType | None:
    """Return the drop session of a CurrentDrop response, or None when it or the user is null."""
    return get_field(response, "data", "currentUser", "dropCurrentSession")


def claim_succeeded(response: JsonType) -> bool:
    """Return True when a ClaimDrop response reports the drop claimed, and False when its data is null."""
    data = get_field(response, "data")
    if not isinstance(data, dict) or data.get("errors"):
        return False
    return get_field(data, "claimDropRewards", "status") in CLAIMED_STATUSES
