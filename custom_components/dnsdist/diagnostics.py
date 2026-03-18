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
        if not hasattr(coordinator, "data"):
            continue
        try:
            name = getattr(coordinator, "_name", entry_id)
            data = coordinator.data or {}
            system_info[name] = {
                "data": data,
                "last_update_success": coordinator.last_update_success,
            }
        except Exception as err:
            system_info[entry_id] = {"error": str(err)}

    return {"dnsdist": system_info}
