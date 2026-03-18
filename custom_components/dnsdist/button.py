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

"""Buttons for PowerDNS dnsdist integration (REST-only actions)."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_IS_GROUP, CONF_MEMBERS, DOMAIN
from .utils import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up dnsdist action buttons for a host or group."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    is_group = bool(entry.data.get(CONF_IS_GROUP))
    members: list[str] = list(entry.data.get(CONF_MEMBERS, [])) if is_group else []

    entities: list[DnsdistActionButton] = [
        ClearCacheButton(coordinator, entry.entry_id, is_group=is_group, members=members),
    ]
    async_add_entities(entities)


class DnsdistActionButton(CoordinatorEntity, ButtonEntity):
    """Base class for dnsdist action buttons."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_requires_action_confirmation = True  # HA 2025.10+

    def __init__(self, coordinator, entry_id: str, *, is_group: bool, members: list[str]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._is_group = is_group
        self._members = members or []

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self.coordinator, self._is_group)

    async def _targets(self) -> AsyncIterator[str | None]:
        if self._is_group and self._members:
            for m in self._members:
                yield m
        else:
            yield getattr(self.coordinator, "_name", None)

    async def _call_service(self, service: str, *, host: str | None = None, **data: Any) -> None:
        payload = dict(data)
        if host:
            payload["host"] = host
        await self.hass.services.async_call(DOMAIN, service, payload, blocking=True)


class ClearCacheButton(DnsdistActionButton):
    """Button to clear cache on a host or across a group."""

    _attr_translation_key = "clear_cache"
    _attr_icon = "mdi:database-refresh"

    def __init__(self, coordinator, entry_id: str, *, is_group: bool, members: list[str]) -> None:
        super().__init__(coordinator, entry_id, is_group=is_group, members=members)
        self._attr_unique_id = f"{entry_id}:btn_clear_cache"

    async def async_press(self) -> None:
        async for target in self._targets():
            await self._call_service("clear_cache", host=target)
