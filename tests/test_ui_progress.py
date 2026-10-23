from __future__ import annotations

from fakes import FakeTwitch, campaign_data, drop_data
from gqldata import complete_campaigns
from inventory import DropsCampaign


def test_the_main_tab_shows_no_text_for_a_campaign_name_that_a_server_error_set_to_null(window):
    fake = FakeTwitch()
    data = complete_campaigns({"c1": {**campaign_data([drop_data("d1")]), "name": None}})["c1"]
    gui = window(fake)

    gui.display_drop(DropsCampaign(fake, data, {}).timed_drops["d1"], countdown=False)

    assert gui.progress._vars["campaign"]["name"].get() == ""
