"""Read GQL response data, in which a server error leaves the field it names null."""
from __future__ import annotations

from itertools import chain
from typing import Any, TYPE_CHECKING

from exceptions import MinerException

if TYPE_CHECKING:
    from constants import JsonType


# DropsCampaign reads these, and a campaign whose details are null may lack them
CAMPAIGN_FIELDS = ("game", "allow", "timeBasedDrops")


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


def campaign_details(responses: list[JsonType]) -> dict[str, JsonType]:
    """Return the campaigns of CampaignDetails responses by ID, leaving out a null one."""
    details: dict[str, JsonType] = {}
    for response in responses:
        campaign = get_field(response, "data", "user", "dropCampaign")
        if campaign is not None:
            details[campaign["id"]] = campaign
    return details


def complete_campaigns(campaigns: dict[str, JsonType]) -> dict[str, JsonType]:
    """Return the campaigns in which none of CAMPAIGN_FIELDS is null or missing."""
    return {
        campaign_id: campaign
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
