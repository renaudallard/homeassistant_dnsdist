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

from unittest.mock import MagicMock

from custom_components.dnsdist.const import DOMAIN
from custom_components.dnsdist.services import _host_targets


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
