from __future__ import annotations

from channel import Channel
from fakes import FakeTwitch


def test_a_channel_added_again_is_the_object_that_the_selection_returns(window):
    fake = FakeTwitch()
    channels = window(fake).channels
    old, new = Channel(fake, id=1, login="c1"), Channel(fake, id=1, login="c1")
    channels.display(old, add=True)
    channels.display(new, add=True)
    channels.set_selection(new)

    assert channels.get_selection() is new
