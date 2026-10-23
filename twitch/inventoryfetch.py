"""The mixin of `Twitch` that fetches the inventory and the campaigns, and builds the campaign list from them."""
from __future__ import annotations

import json
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from translate import _
from inventory import DropsCampaign
from exceptions import ExitRequest
from gqldata import (
    merge_data,
    user_inventory,
    campaign_details,
    campaign_summaries,
    complete_campaigns,
)
from utils import chunk, timestamp
from constants import DUMP_PATH
from twitchapi import GQL_QUERIES

if TYPE_CHECKING:
    from collections import abc, deque

    from gui import GUIManager
    from settings import Settings
    from inventory import TimedDrop
    from constants import JsonType

    from .session import _AuthState


class InventoryFetchMixin:
    """The methods of `Twitch` that fetch the inventory and the campaigns."""

    settings: Settings
    gui: GUIManager
    inventory: list[DropsCampaign]
    _drops: dict[str, TimedDrop]
    _campaigns: dict[str, DropsCampaign]
    _mnt_triggers: deque[datetime]
    _mnt_task: asyncio.Task[None] | None
    _maintenance_task: abc.Callable[[], abc.Coroutine[Any, Any, None]]
    get_auth: abc.Callable[[], abc.Coroutine[Any, Any, _AuthState]]
    gql_request: abc.Callable[..., abc.Coroutine[Any, Any, Any]]

    async def fetch_campaigns(
        self, campaigns_chunk: list[tuple[str, JsonType]]
    ) -> dict[str, JsonType]:
        campaign_ids: dict[str, JsonType] = dict(campaigns_chunk)
        auth_state = await self.get_auth()
        response_list: list[JsonType] = await self.gql_request(
            [
                GQL_QUERIES["CampaignDetails"].with_variables(
                    {"channelLogin": str(auth_state.user_id), "dropID": cid}
                )
                for cid in campaign_ids
            ]
        )
        return merge_data(campaign_ids, campaign_details(list(campaign_ids), response_list))

    async def fetch_inventory(self) -> None:
        status_update = self.gui.status.update
        status_update(_("gui", "status", "fetching_inventory"))
        # fetch in-progress campaigns (inventory)
        response = await self.gql_request(GQL_QUERIES["Inventory"])
        inventory: JsonType = user_inventory(response)
        ongoing_campaigns: list[JsonType] = inventory["dropCampaignsInProgress"]
        # this contains claimed benefit edge IDs, not drop IDs
        claimed_benefits: dict[str, datetime] = {
            b["id"]: timestamp(b["lastAwardedAt"]) for b in inventory["gameEventDrops"]
        }
        inventory_data: dict[str, JsonType] = {c["id"]: c for c in ongoing_campaigns}
        # fetch general available campaigns data (campaigns)
        response = await self.gql_request(GQL_QUERIES["Campaigns"])
        available_campaigns: dict[str, JsonType] = campaign_summaries(response)
        # fetch detailed data for each campaign, in chunks
        status_update(_("gui", "status", "fetching_campaigns"))
        fetch_campaigns_tasks: list[asyncio.Task[Any]] = [
            asyncio.create_task(self.fetch_campaigns(campaigns_chunk))
            for campaigns_chunk in chunk(available_campaigns.items(), 20)
        ]
        try:
            for coro in asyncio.as_completed(fetch_campaigns_tasks):
                chunk_campaigns_data = await coro
                # merge the inventory and campaigns datas together
                inventory_data = merge_data(inventory_data, chunk_campaigns_data)
        except Exception:
            # asyncio.as_completed doesn't cancel tasks on errors
            for task in fetch_campaigns_tasks:
                task.cancel()
            raise
        inventory_data = complete_campaigns(inventory_data)

        if self.settings.dump:
            # dump the campaigns data to the dump file
            with open(DUMP_PATH, 'a', encoding="utf8") as file:
                # we need to pre-process the inventory dump a little
                dump_data: JsonType = deepcopy(inventory_data)
                for campaign_data in dump_data.values():
                    # replace ACL lists with a simple text description
                    if (
                        campaign_data["allow"]
                        and campaign_data["allow"].get("isEnabled", True)
                        and campaign_data["allow"]["channels"]
                    ):
                        # simply count the channels included in the ACL
                        campaign_data["allow"]["channels"] = (
                            f"{len(campaign_data['allow']['channels'])} channels"
                        )
                    # replace drop instance IDs, so they don't include user IDs
                    for drop_data in campaign_data["timeBasedDrops"]:
                        if "self" in drop_data and drop_data["self"]["dropInstanceID"]:
                            drop_data["self"]["dropInstanceID"] = "..."
                json.dump(dump_data, file, indent=4, sort_keys=True)
                file.write("\n\n")  # add 2x new line spacer
                json.dump(inventory["gameEventDrops"], file, indent=4, sort_keys=True, default=str)

        # use the merged data to create campaign objects
        campaigns: list[DropsCampaign] = [
            DropsCampaign(self, campaign_data, claimed_benefits)
            for campaign_data in inventory_data.values()
        ]
        campaigns.sort(key=lambda c: c.active, reverse=True)
        campaigns.sort(key=lambda c: c.upcoming and c.starts_at or c.ends_at)
        campaigns.sort(key=lambda c: c.eligible, reverse=True)

        self._drops.clear()
        self._campaigns.clear()
        self.gui.inv.clear()
        self.inventory.clear()
        self._mnt_triggers.clear()
        switch_triggers: set[datetime] = set()
        next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
        # add the campaigns to the internal inventory
        for campaign in campaigns:
            self._drops.update({drop.id: drop for drop in campaign.drops})
            if campaign.can_earn_within(next_hour):
                switch_triggers.update(campaign.time_triggers)
            self.inventory.append(campaign)
            self._campaigns[campaign.id] = campaign
        # concurrently add the campaigns into the GUI
        # NOTE: this fetches pictures from the CDN, so might be slow without a cache
        status_update(
            _("gui", "status", "adding_campaigns").format(counter=f"(0/{len(campaigns)})")
        )
        add_campaign_tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(self.gui.inv.add_campaign(campaign))
            for campaign in campaigns
        ]
        try:
            for i, coro in enumerate(asyncio.as_completed(add_campaign_tasks), start=1):
                await coro
                status_update(
                    _("gui", "status", "adding_campaigns").format(
                        counter=f"({i}/{len(campaigns)})"
                    )
                )
                # this is needed here explicitly, because cache reads from disk don't raise this
                if self.gui.close_requested:
                    raise ExitRequest()
        except Exception:
            # asyncio.as_completed doesn't cancel tasks on errors
            for task in add_campaign_tasks:
                task.cancel()
            raise
        self._mnt_triggers.extend(sorted(switch_triggers))
        # trim out all triggers that we're already past
        now = datetime.now(timezone.utc)
        while self._mnt_triggers and self._mnt_triggers[0] <= now:
            self._mnt_triggers.popleft()
        # NOTE: maintenance task is restarted at the end of each inventory fetch
        if self._mnt_task is not None and not self._mnt_task.done():
            self._mnt_task.cancel()
        self._mnt_task = asyncio.create_task(self._maintenance_task())
