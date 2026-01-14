"""Buttons for PowerDNS dnsdist integration (REST-only actions)."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_IS_GROUP, CONF_MEMBERS

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
        name = getattr(self.coordinator, "_name", "dnsdist")
        identifier = f"group:{name}" if self._is_group else f"host:{name}"
        info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=name,
            manufacturer="PowerDNS",
            model="dnsdist Group" if self._is_group else "dnsdist Host",
        )
        if not self._is_group and hasattr(self.coordinator, "_host"):
            proto = "https" if getattr(self.coordinator, "_use_https", False) else "http"
            info["configuration_url"] = f"{proto}://{self.coordinator._host}:{self.coordinator._port}"
        return info

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
