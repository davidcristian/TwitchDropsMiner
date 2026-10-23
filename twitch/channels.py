"""The mixin of `Twitch` with the states that remove and add the tracked channels, and the order of their slots."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from translate import _
from constants import MAX_INT, MAX_CHANNELS, State
from twitchapi import WebsocketTopic

if TYPE_CHECKING:
    from collections import abc, OrderedDict

    from gui import GUIManager
    from channel import Channel
    from websocket import WebsocketPool
    from inventory import DropsCampaign
    from utils import AwaitableValue, Game
    from constants import JsonType


class ChannelsMixin:
    """The methods of `Twitch` that run `CHANNELS_CLEANUP` and `CHANNELS_FETCH`, which keep the tracked channels."""

    gui: GUIManager
    websocket: WebsocketPool
    inventory: list[DropsCampaign]
    wanted_games: list[Game]
    watching_channel: AwaitableValue[Channel]
    _no_campaign_printed: bool
    print: abc.Callable[[str], None]
    change_state: abc.Callable[[State], None]
    get_priority: abc.Callable[[Channel], int]
    can_watch: abc.Callable[[Channel], bool]
    watch: abc.Callable[..., None]
    stop_watching: abc.Callable[[], None]
    get_active_campaign: abc.Callable[[Channel | None], DropsCampaign | None]
    get_live_streams: abc.Callable[..., abc.Coroutine[Any, Any, list[Channel]]]
    bulk_check_online: abc.Callable[[abc.Iterable[Channel]], abc.Coroutine[Any, Any, None]]
    process_stream_state: abc.Callable[[int, JsonType], abc.Coroutine[Any, Any, None]]
    process_stream_update: abc.Callable[[int, JsonType], abc.Coroutine[Any, Any, None]]

    @staticmethod
    def _viewers_key(channel: Channel) -> int:
        if (viewers := channel.viewers) is not None:
            return viewers
        return -1

    def _slot_order(
        self, channels: list[Channel], acl_priority: dict[Channel, int], selected_id: int | None
    ) -> list[Channel]:
        """
        Returns the channels in the order in which they keep one of the MAX_CHANNELS slots.
        channels is sorted by get_priority, and acl_priority maps a channel to the best priority of the wanted
        games whose campaigns list it in their ACL.
        """
        best = next((self.get_priority(channel) for channel in channels if self.can_watch(channel)), None)

        def key(channel: Channel) -> tuple[bool, int]:
            priority = self.get_priority(channel)
            # CHANNEL_SWITCH watches one of these next, so they keep their slots first
            if (priority == best or channel.id == selected_id) and self.can_watch(channel):
                return (False, priority)
            # An offline ACL channel, or one that streams another game, ranks with the game of its campaign, ahead of
            # the live channels of games with a lower priority, so it keeps the subscription to its stream-up event.
            if priority == MAX_INT:
                priority = acl_priority.get(channel, MAX_INT)
            return (True, priority)

        return sorted(channels, key=key)

    def _run_channels_cleanup(
        self, channels: OrderedDict[int, Channel], full_cleanup: bool
    ) -> tuple[bool, int | None]:
        """
        Run State.CHANNELS_CLEANUP: remove every channel on a full cleanup or when no game is wanted, else the
        channels without an ACL that are offline or stream a game that is not wanted.
        Returns full_cleanup, now False, and the ID of the selected channel when this removed it.
        """
        self.gui.status.update(_("gui", "status", "cleanup"))
        if not self.wanted_games or full_cleanup:
            # no games selected or we're doing full cleanup: remove everything
            to_remove_channels: list[Channel] = list(channels.values())
        else:
            # remove all channels that:
            to_remove_channels = [
                channel
                for channel in channels.values()
                if (
                    not channel.acl_based  # aren't ACL-based
                    and (
                        channel.offline  # and are offline
                        # or online but aren't streaming the game we want anymore
                        or (channel.game is None or channel.game not in self.wanted_games)
                    )
                )
            ]
        full_cleanup = False
        # removing a channel's row drops its selection, which the fetch restores when it adds the channel back
        selection = self.gui.channels.get_selection()
        removed_selection = (
            selection.id if selection is not None and selection in to_remove_channels else None
        )
        if to_remove_channels:
            to_remove_topics: list[str] = []
            for channel in to_remove_channels:
                to_remove_topics.append(
                    WebsocketTopic.as_str("Channel", "StreamState", channel.id)
                )
                to_remove_topics.append(
                    WebsocketTopic.as_str("Channel", "StreamUpdate", channel.id)
                )
            self.websocket.remove_topics(to_remove_topics)
            for channel in to_remove_channels:
                del channels[channel.id]
                channel.remove()
            del to_remove_channels, to_remove_topics
        if self.wanted_games:
            self._no_campaign_printed = False
            self.change_state(State.CHANNELS_FETCH)
        else:
            # with no games available, we switch to IDLE after cleanup
            if not self._no_campaign_printed:
                self.print(_("status", "no_campaign"))
                self._no_campaign_printed = True
            self.change_state(State.IDLE)
        return full_cleanup, removed_selection

    async def _run_channels_fetch(
        self, channels: OrderedDict[int, Channel], watch_restarted: bool, removed_selection: int | None
    ) -> bool:
        """
        Run State.CHANNELS_FETCH: add the channels of the wanted games and keep at most MAX_CHANNELS of them.
        Returns watch_restarted, now False.
        """
        self.gui.status.update(_("gui", "status", "gathering"))
        # start with all current channels
        # NOTE: the GUI list is only rebuilt further below, and only if needed
        new_channels: set[Channel] = set(channels.values())
        # gather and add ACL channels from campaigns
        # NOTE: we consider only campaigns that can be progressed
        # NOTE: we use another set so that we can set them online separately
        no_acl: set[Game] = set()
        acl_channels: set[Channel] = set()
        # the best priority of the wanted games whose campaigns list the channel in their ACL
        acl_priority: dict[Channel, int] = {}
        next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
        for campaign in self.inventory:
            if (
                campaign.game in self.wanted_games
                and campaign.can_earn_within(next_hour)
            ):
                if campaign.allowed_channels:
                    acl_channels.update(campaign.allowed_channels)
                    game_priority = self.wanted_games.index(campaign.game)
                    for channel in campaign.allowed_channels:
                        acl_priority[channel] = min(game_priority, acl_priority.get(channel, game_priority))
                else:
                    no_acl.add(campaign.game)
        # remove all ACL channels that already exist from the other set
        acl_channels.difference_update(new_channels)
        # use the other set to set them online if possible
        await self.bulk_check_online(acl_channels)
        # finally, add them as new channels
        new_channels.update(acl_channels)
        for game in no_acl:
            # for every campaign without an ACL, for it's game,
            # add a list of live channels with drops enabled
            new_channels.update(await self.get_live_streams(game, drops_enabled=True))
        # sort them descending by viewers, by priority and by game priority
        # NOTE: Viewers sort also ensures ONLINE channels are sorted to the top
        # NOTE: We can drop using the set now, because there's no more channels being added
        ordered_channels: list[Channel] = sorted(
            new_channels, key=self._viewers_key, reverse=True
        )
        ordered_channels.sort(key=lambda ch: ch.acl_based, reverse=True)
        ordered_channels.sort(key=self.get_priority)
        # ensure that we won't end up with more channels than we can handle,
        # keeping the list in this order
        selection = self.gui.channels.get_selection()
        kept_channels = set(
            self._slot_order(
                ordered_channels,
                acl_priority,
                selection.id if selection is not None else removed_selection,
            )[:MAX_CHANNELS]
        )
        to_remove_channels = [ch for ch in ordered_channels if ch not in kept_channels]
        ordered_channels = [ch for ch in ordered_channels if ch in kept_channels]
        if to_remove_channels:
            # the tracked channels and the gui list are replaced below,
            # so unsubscribe from their topics and cancel their online checks
            to_remove_topics = []
            for channel in to_remove_channels:
                channel.cancel_online_check()
                to_remove_topics.append(
                    WebsocketTopic.as_str("Channel", "StreamState", channel.id)
                )
                to_remove_topics.append(
                    WebsocketTopic.as_str("Channel", "StreamUpdate", channel.id)
                )
            self.websocket.remove_topics(to_remove_topics)
            del to_remove_channels, to_remove_topics
        # Only tear the gui list down when the set of channels actually changed.
        # A periodic refresh usually ends up with the exact same channels, and
        # rebuilding the table every time would flicker and drop the user's selection.
        gui_selection: Channel | None = None
        if self.gui.channels.get_iids() != set(
            channel.iid for channel in ordered_channels
        ):
            gui_selection = selection
            self.gui.channels.clear()
        # set our new channel list
        # NOTE: a stream event during the awaits above looks up its channel in this map,
        # so the old channels stay in it until no await is left
        channels.clear()
        for channel in ordered_channels:
            channels[channel.id] = channel
            channel.display(add=True)
        # restore the selection, or the one the cleanup removed, as long as the channel is still on the list
        selection_id = gui_selection.id if gui_selection is not None else removed_selection
        if selection_id is not None and selection_id in channels:
            self.gui.channels.set_selection(channels[selection_id])
        # subscribe to these channel's state updates
        to_add_topics: list[WebsocketTopic] = []
        for channel_id in channels:
            to_add_topics.append(
                WebsocketTopic(
                    "Channel", "StreamState", channel_id, self.process_stream_state
                )
            )
            to_add_topics.append(
                WebsocketTopic(
                    "Channel", "StreamUpdate", channel_id, self.process_stream_update
                )
            )
        self.websocket.add_topics(to_add_topics)
        # relink watching channel after cleanup,
        # or stop watching it if it no longer qualifies
        # NOTE: this replaces 'self.watching_channel's internal value with the new object
        watching_channel = self.watching_channel.get_with_default(None)
        if watching_channel is not None:
            new_watching: Channel | None = channels.get(watching_channel.id)
            if new_watching is not None and self.can_watch(new_watching):
                self.watch(new_watching, update_status=False)
            else:
                # we've removed a channel we were watching
                self.stop_watching()
            del new_watching
        # Show the active drop one minute lower when a watch starts or GAMES_UPDATE restarted it.
        # This stops the countdown, so a refresh that keeps the watched channel skips it.
        if watch_restarted or not self.watching_channel.has_value():
            for channel in channels.values():
                # check if there's any channels we can watch first
                if self.can_watch(channel):
                    if (
                        (active_campaign := self.get_active_campaign(channel)) is not None
                        and (active_drop := active_campaign.first_drop) is not None
                    ):
                        active_drop.display(countdown=False, subone=True)
                    break
        watch_restarted = False
        self.change_state(State.CHANNEL_SWITCH)
        del (
            no_acl,
            acl_channels,
            acl_priority,
            kept_channels,
            new_channels,
            to_add_topics,
            ordered_channels,
            watching_channel,
        )
        return watch_restarted
