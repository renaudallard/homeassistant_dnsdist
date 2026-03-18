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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_BACKENDS, CONF_IS_GROUP, DOMAIN
from .utils import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up dnsdist backend binary sensors for a host."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    is_group = bool(entry.data.get(CONF_IS_GROUP))

    if is_group:
        return

    backend_entities: dict[str, DnsdistBackendBinarySensor] = {}

    @callback
    def _async_sync_backends() -> None:
        if not coordinator.data:
            return
        backends = coordinator.data.get(ATTR_BACKENDS)
        if not isinstance(backends, dict):
            backends = {}

        current_slugs = set(backends.keys())
        known_slugs = set(backend_entities.keys())

        removed_slugs = known_slugs - current_slugs
        ent_reg = er.async_get(hass)
        for slug in removed_slugs:
            entity = backend_entities.pop(slug, None)
            if entity:
                if entity.entity_id and ent_reg.async_get(entity.entity_id):
                    ent_reg.async_remove(entity.entity_id)
                else:
                    hass.async_create_task(entity.async_remove())

        new_entities: list[DnsdistBackendBinarySensor] = []
        for slug in current_slugs:
            if slug in backend_entities:
                continue
            entity = DnsdistBackendBinarySensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                backend_slug=slug,
            )
            backend_entities[slug] = entity
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    _async_sync_backends()
    entry.async_on_unload(coordinator.async_add_listener(_async_sync_backends))


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
