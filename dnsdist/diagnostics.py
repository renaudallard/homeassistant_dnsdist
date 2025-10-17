"""Diagnostics support for PowerDNS dnsdist integration."""

from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Fields to remove from exported diagnostics (sensitive)
TO_REDACT = {"api_key", "X-API-Key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a single dnsdist config entry."""
    data = dict(entry.data)
    data = async_redact_data(data, TO_REDACT)

    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    diagnostics: dict = {
        "config": data,
        "entry_type": data.get("type", "server"),
    }

    if coordinator is None:
        diagnostics["error"] = "Coordinator not initialized"
        return diagnostics

    # include normalized or aggregated data
    try:
        current_data = coordinator.data or {}
        diagnostics["data"] = current_data
        diagnostics["last_update_success"] = coordinator.last_update_success
    except Exception as err:
        _LOGGER.warning("Failed to collect diagnostics for %s: %s", entry.title, err)
        diagnostics["error"] = str(err)

    return diagnostics


async def async_get_system_diagnostics(hass: HomeAssistant) -> dict:
    """Return overall dnsdist diagnostics for all entries."""
    all_entries = hass.data.get(DOMAIN, {})
    if not all_entries:
        return {"dnsdist": "No active coordinators"}

    system_info = {}
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
