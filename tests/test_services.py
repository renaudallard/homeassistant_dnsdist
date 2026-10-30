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

"""Tests for the dnsdist service helpers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dnsdist.button import ClearCacheButton
from custom_components.dnsdist.const import DOMAIN
from custom_components.dnsdist.services import _host_targets, register_dnsdist_services


def make_coord(name, *, is_host=True):
    """Build a coordinator stub. Only hosts carry a _host attribute."""
    coord = MagicMock(spec=["_name", "_host"] if is_host else ["_name"])
    coord._name = name
    if is_host:
        coord._host = "10.0.0.1"
    return coord


def targets(coords, target):
    hass = MagicMock()
    hass.data = {DOMAIN: {f"entry-{i}": c for i, c in enumerate(coords)}}
    return [c._name for c in _host_targets(hass, target)]


class TestHostTargets:
    def test_no_target_hits_every_host(self):
        coords = [make_coord("dns1"), make_coord("dns2")]
        assert targets(coords, None) == ["dns1", "dns2"]

    def test_no_target_leaves_groups_out(self):
        coords = [make_coord("dns1"), make_coord("all", is_host=False)]
        assert targets(coords, None) == ["dns1"]

    def test_exact_display_name(self):
        coords = [make_coord("DNS 1"), make_coord("DNS 2")]
        assert targets(coords, "DNS 1") == ["DNS 1"]

    def test_entity_id_spelling_finds_the_host(self):
        """The card only knows the slug, not the display name."""
        assert targets([make_coord("DNS 1")], "dns_1") == ["DNS 1"]

    def test_a_group_is_never_a_target(self):
        coords = [make_coord("all", is_host=False)]
        assert targets(coords, "all") == []

    def test_unknown_name_hits_nothing(self):
        assert targets([make_coord("dns1")], "nope") == []

    def test_an_exact_match_wins_over_a_slug_match(self):
        coords = [make_coord("DNS 1"), make_coord("DNS-1")]
        assert targets(coords, "DNS 1") == ["DNS 1"]

    def test_no_hosts_at_all(self):
        assert targets([], None) == []


class TestClearCache:
    """A failure has to reach the caller, or it looks like a cleared cache."""

    def clear(self, coords, api, host=None):
        hass = MagicMock()
        hass.data = {DOMAIN: {f"entry-{i}": c for i, c in enumerate(coords)}}
        with patch("custom_components.dnsdist.services.async_register_admin_service") as register:
            asyncio.run(register_dnsdist_services(hass))
        handler = register.call_args.args[3]
        call = MagicMock(data={"host": host} if host else {})
        with patch("custom_components.dnsdist.services._call_dnsdist_api", api):
            asyncio.run(handler(call))

    def test_success_raises_nothing(self):
        api = AsyncMock(side_effect=[(200, ""), (204, "")])
        self.clear([make_coord("dns1"), make_coord("dns2")], api)
        assert api.call_count == 2

    def test_a_failure_is_reported_after_every_host_had_its_turn(self):
        api = AsyncMock(side_effect=[(401, "unauthorized"), (200, ""), (-1, "timeout")])
        with pytest.raises(HomeAssistantError, match=r"dns1 \(HTTP 401\), dns3 \(timeout\)"):
            self.clear([make_coord("dns1"), make_coord("dns2"), make_coord("dns3")], api)
        assert api.call_count == 3

    def test_an_unknown_host_is_an_error(self):
        with pytest.raises(HomeAssistantError, match="nope"):
            self.clear([make_coord("dns1")], AsyncMock(), host="nope")

    def test_no_hosts_at_all_is_an_error(self):
        with pytest.raises(HomeAssistantError):
            self.clear([], AsyncMock())


class TestClearCacheButton:
    def test_a_group_clears_every_member_before_reporting(self):
        with patch("homeassistant.helpers.frame.report_usage"):
            button = ClearCacheButton(MagicMock(), "e", is_group=True, members=["dns1", "dns2", "dns3"])
        calls = []

        async def service(domain, name, payload, blocking):
            calls.append(payload["host"])
            if payload["host"] != "dns2":
                raise HomeAssistantError(f"failed on {payload['host']}")

        button.hass = MagicMock()
        button.hass.services.async_call = service
        with pytest.raises(HomeAssistantError, match="failed on dns1; failed on dns3"):
            asyncio.run(button.async_press())
        assert calls == ["dns1", "dns2", "dns3"]
