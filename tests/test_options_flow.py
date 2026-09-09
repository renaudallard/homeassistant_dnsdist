# Copyright (c) 2025, Renaud Allard <renaud@allard.it>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Tests for the options flow helpers."""

from unittest.mock import MagicMock

from custom_components.dnsdist.const import CONF_IS_GROUP, CONF_MEMBERS, CONF_NAME
from custom_components.dnsdist.options_flow import _rename_group_members


def make_entry(title, data):
    entry = MagicMock()
    entry.title = title
    entry.data = data
    return entry


def rename(entries, old_name, new_name):
    """Run the rename against a fake config entry store and return the updates."""
    updates = {}
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = entries
    hass.config_entries.async_update_entry.side_effect = lambda entry, **kw: updates.update({entry.title: kw})
    _rename_group_members(hass, old_name, new_name)
    return updates


class TestRenameGroupMembers:
    def test_group_follows_the_rename(self):
        group = make_entry("all", {CONF_IS_GROUP: True, CONF_MEMBERS: ["dns1", "dns2"]})
        updates = rename([group], "dns1", "resolver")
        assert updates["all"]["data"][CONF_MEMBERS] == ["resolver", "dns2"]

    def test_group_without_the_member_is_left_alone(self):
        group = make_entry("all", {CONF_IS_GROUP: True, CONF_MEMBERS: ["dns2"]})
        assert rename([group], "dns1", "resolver") == {}

    def test_host_entries_are_left_alone(self):
        host = make_entry("dns1", {CONF_IS_GROUP: False, CONF_NAME: "dns1"})
        assert rename([host], "dns1", "resolver") == {}

    def test_every_group_holding_the_member_is_updated(self):
        entries = [
            make_entry("a", {CONF_IS_GROUP: True, CONF_MEMBERS: ["dns1"]}),
            make_entry("b", {CONF_IS_GROUP: True, CONF_MEMBERS: ["dns1", "dns3"]}),
        ]
        updates = rename(entries, "dns1", "resolver")
        assert updates["a"]["data"][CONF_MEMBERS] == ["resolver"]
        assert updates["b"]["data"][CONF_MEMBERS] == ["resolver", "dns3"]

    def test_the_rest_of_the_group_data_survives(self):
        group = make_entry("all", {CONF_IS_GROUP: True, CONF_MEMBERS: ["dns1"], CONF_NAME: "all"})
        data = rename([group], "dns1", "resolver")["all"]["data"]
        assert data[CONF_NAME] == "all"
        assert data[CONF_IS_GROUP] is True
