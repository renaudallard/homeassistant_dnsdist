"""Diagnostics support for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

# Fields to remove from exported diagnostics (sensitive)
TO_REDACT = {CONF_API_KEY, "X-API-Key"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a single config entry."""
    data = dict(entry.data)
    diagnostics: dict[str, Any] = {
        "config": async_redact_data(data, TO_REDACT),
        "entry_type": "group" if data.get("is_group") else "host",
    }

    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        diagnostics["error"] = "Coordinator not initialized"
        return diagnostics

    try:
        current_data = coordinator.data or {}
        diagnostics["data"] = current_data
        diagnostics["last_update_success"] = coordinator.last_update_success
    except Exception as err:
        _LOGGER.warning("Failed to collect diagnostics for %s: %s", entry.title, err)
        diagnostics["error"] = str(err)

    return diagnostics


async def async_get_system_diagnostics(hass: HomeAssistant) -> dict[str, Any]:
    """Return overall dnsdist diagnostics for all entries."""
    all_entries = hass.data.get(DOMAIN, {})
    if not all_entries:
        return {"dnsdist": "No active coordinators"}

    system_info: dict[str, Any] = {}
    for entry_id, coordinator in all_entries.items():
        try:
            name = getattr(coordinator, "_name", entry_id)
            data = coordinator.data or {}
            system_info[name] = {
                "data": data,
                "last_update_success": coordinator.last_update_success,
            }
        except Exception as err:
            system_info[name] = {"error": str(err)}

    return {"dnsdist": system_info}
