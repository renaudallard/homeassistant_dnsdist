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
from custom_components.dnsdist.utils import name_is_taken


def make_entry(title, data):
    entry = MagicMock()
    entry.title = title
    entry.data = data
    entry.entry_id = f"entry-{title}"
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


class TestNameIsTaken:
    def taken(self, entries, name, entry_id=None):
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = entries
        return name_is_taken(hass, name, entry_id=entry_id)

    def test_free_name(self):
        entries = [make_entry("dns1", {CONF_NAME: "dns1"})]
        assert self.taken(entries, "dns2") is False

    def test_name_used_by_another_host(self):
        entries = [make_entry("dns1", {CONF_NAME: "dns1"})]
        assert self.taken(entries, "dns1") is True

    def test_name_used_by_a_group(self):
        entries = [make_entry("all", {CONF_IS_GROUP: True, CONF_NAME: "all"})]
        assert self.taken(entries, "all") is True

    def test_the_entry_being_renamed_does_not_clash_with_itself(self):
        entry = make_entry("dns1", {CONF_NAME: "dns1"})
        entry.entry_id = "e1"
        assert self.taken([entry], "dns1", entry_id="e1") is False

    def test_entry_title_stands_in_for_a_missing_name(self):
        assert self.taken([make_entry("dns1", {})], "dns1") is True
