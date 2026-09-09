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

"""Binary sensors for PowerDNS dnsdist backend health monitoring."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_BACKENDS, ATTR_MEMBERS, DOMAIN
from .utils import async_register_slug_platform, build_device_info, is_group_entry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up backend health for a host, or member reachability for a group."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    if is_group_entry(entry):
        async_register_slug_platform(
            hass,
            entry,
            coordinator,
            async_add_entities,
            data_key=ATTR_MEMBERS,
            factory=lambda slug: DnsdistMemberBinarySensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                member_slug=slug,
            ),
        )
        return

    async_register_slug_platform(
        hass,
        entry,
        coordinator,
        async_add_entities,
        data_key=ATTR_BACKENDS,
        factory=lambda slug: DnsdistBackendBinarySensor(
            coordinator=coordinator,
            entry_id=entry.entry_id,
            backend_slug=slug,
        ),
    )


class DnsdistBackendBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor tracking whether a dnsdist backend is healthy."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, *, coordinator, entry_id: str, backend_slug: str) -> None:
        super().__init__(coordinator)
        self._slug = backend_slug
        self._attr_unique_id = f"{entry_id}:backend:{backend_slug}"

    def _backend_data(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        backends = data.get(ATTR_BACKENDS, {}) if isinstance(data, dict) else {}
        if isinstance(backends, dict):
            return backends.get(self._slug, {})
        return {}

    @property
    def name(self) -> str:
        host = getattr(self.coordinator, "_name", "dnsdist")
        backend = self._backend_data()
        address = backend.get("address") or self._slug
        name = backend.get("name")
        if name:
            return f"{host} Backend {name} ({address})"
        return f"{host} Backend {address}"

    @property
    def is_on(self) -> bool | None:
        backend = self._backend_data()
        if not backend:
            return None
        state = str(backend.get("state", "")).lower()
        return state == "up"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        backend = self._backend_data()
        attrs: dict[str, Any] = {}
        for key in ("address", "name", "state", "order", "weight", "pools", "latency"):
            if key in backend and backend[key] is not None:
                attrs[key] = backend[key]
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self.coordinator, False)


class DnsdistMemberBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor tracking whether a group member is still answering.

    A host that stops answering keeps publishing its last known figures, so
    without this the group would go on aggregating a dead member in silence.
    """

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, *, coordinator, entry_id: str, member_slug: str) -> None:
        super().__init__(coordinator)
        self._slug = member_slug
        self._attr_unique_id = f"{entry_id}:member:{member_slug}"

    def _member_data(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        members = data.get(ATTR_MEMBERS, {}) if isinstance(data, dict) else {}
        if isinstance(members, dict):
            return members.get(self._slug, {})
        return {}

    @property
    def name(self) -> str:
        group = getattr(self.coordinator, "_name", "dnsdist")
        member = self._member_data().get("name") or self._slug
        return f"{group} Member {member}"

    @property
    def is_on(self) -> bool | None:
        """Report None while the member entry is not loaded, which is not a failure."""
        reachable = self._member_data().get("reachable")
        return reachable if isinstance(reachable, bool) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        member = self._member_data()
        return {key: member[key] for key in ("name", "loaded") if key in member}

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self.coordinator, True)
