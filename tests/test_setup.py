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

"""Tests for the entry setup helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dnsdist import (
    _async_register_frontend,
    _async_unregister_lovelace_module,
    _clamp_update_interval,
)
from custom_components.dnsdist.const import (
    DEFAULT_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)


class TestClampUpdateInterval:
    """A stored zero used to divide by zero and take the whole entry down."""

    @pytest.mark.parametrize("value", [0, -5, 1, MIN_UPDATE_INTERVAL - 1])
    def test_too_small_comes_up_to_the_minimum(self, value):
        assert _clamp_update_interval(value) == MIN_UPDATE_INTERVAL

    @pytest.mark.parametrize("value", [MAX_UPDATE_INTERVAL + 1, 9999])
    def test_too_large_comes_down_to_the_maximum(self, value):
        assert _clamp_update_interval(value) == MAX_UPDATE_INTERVAL

    @pytest.mark.parametrize("value", [MIN_UPDATE_INTERVAL, 30, 45, MAX_UPDATE_INTERVAL])
    def test_a_value_in_range_is_left_alone(self, value):
        assert _clamp_update_interval(value) == value

    def test_a_numeric_string_is_taken(self):
        assert _clamp_update_interval("45") == 45

    @pytest.mark.parametrize("value", ["nope", None, [], {}])
    def test_anything_unreadable_falls_back_to_the_default(self, value):
        assert _clamp_update_interval(value) == DEFAULT_UPDATE_INTERVAL

    def test_the_result_can_always_size_the_history_deque(self):
        """That division is what used to raise before the coordinator existed."""
        for value in (0, -5, "nope", None, 9999, 30):
            assert 86400 // _clamp_update_interval(value) > 0


class TestCardResource:
    """Lovelace calls the resource mode resource_mode from 2026.2, mode before."""

    def registered(self, lovelace):
        hass = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()
        hass.data = {"lovelace": lovelace}
        with patch("custom_components.dnsdist._async_register_lovelace_module", AsyncMock()) as register:
            asyncio.run(_async_register_frontend(hass))
        return register.called

    @pytest.mark.parametrize("field", ["resource_mode", "mode"])
    def test_storage_mode_registers_the_card(self, field):
        assert self.registered(SimpleNamespace(**{field: "storage"})) is True

    @pytest.mark.parametrize("field", ["resource_mode", "mode"])
    def test_yaml_mode_leaves_it_to_the_user(self, field):
        assert self.registered(SimpleNamespace(**{field: "yaml"})) is False


class TestCardResourceRemoval:
    def remove(self, items, mode="storage"):
        resources = MagicMock(loaded=False)
        resources.async_load = AsyncMock()
        resources.async_items.return_value = items
        resources.async_delete_item = AsyncMock()
        hass = MagicMock()
        hass.data = {"lovelace": SimpleNamespace(resource_mode=mode, resources=resources)}
        asyncio.run(_async_unregister_lovelace_module(hass))
        return resources

    def test_only_our_resource_goes(self):
        resources = self.remove(
            [
                {"id": "a", "url": "/dnsdist_static/dnsdist-card.js?v=1.5.5"},
                {"id": "b", "url": "/local/other-card.js"},
            ]
        )
        resources.async_load.assert_awaited_once()
        resources.async_delete_item.assert_awaited_once_with("a")

    def test_yaml_mode_is_left_to_the_user(self):
        resources = self.remove([{"id": "a", "url": "/dnsdist_static/dnsdist-card.js"}], mode="yaml")
        resources.async_delete_item.assert_not_called()
