# 202510231130
"""Service registration for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# ============================================================
# Helper: Generic API Caller
# ============================================================

async def _call_dnsdist_api(coordinator, method: str, endpoint: str, json_data: dict | None = None) -> bool:
    """Call a dnsdist API endpoint for a given host coordinator."""
    if not hasattr(coordinator, "_base_url"):
        return False
    base = coordinator._base_url
    headers: dict[str, str] = {}
    if getattr(coordinator, "_api_key", None):
        headers["X-API-Key"] = coordinator._api_key

    url = f"{base}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            req = getattr(session, method.lower())
            async with req(url, headers=headers, ssl=getattr(coordinator, "_verify_ssl", True), json=json_data, timeout=10) as resp:
                if resp.status in (200, 204):
                    return True
                _LOGGER.warning("[%s] API %s %s -> HTTP %s", coordinator._name, method, endpoint, resp.status)
    except Exception as err:
        _LOGGER.error("[%s] dnsdist API call error: %s", coordinator._name, err)
    return False


# ============================================================
# Service Registration
# ============================================================

async def register_dnsdist_services(hass: HomeAssistant):
    """Register all dnsdist services."""

    async def _get_target_coordinators(target: str | None):
        """Return coordinators matching a given host name or all."""
        coords = list(hass.data.get(DOMAIN, {}).values())
        # Filter only host coordinators (not groups)
        coords = [c for c in coords if hasattr(c, "_host")]
        if not target:
            return coords
        return [c for c in coords if getattr(c, "_name", None) == target]

    # ------------------------------------------------------------
    # clear_cache
    # ------------------------------------------------------------

    async def handle_clear_cache(call: ServiceCall):
        target = call.data.get("host")
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "POST", "/api/v1/clearCache")

    # ------------------------------------------------------------
    # enable_server
    # ------------------------------------------------------------

    async def handle_enable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target or not backend:
            _LOGGER.warning("enable_server requires both host and backend")
            return
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{backend}/enable")

    # ------------------------------------------------------------
    # disable_server
    # ------------------------------------------------------------

    async def handle_disable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target or not backend:
            _LOGGER.warning("disable_server requires both host and backend")
            return
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{backend}/disable")

    # ------------------------------------------------------------
    # reload_config
    # ------------------------------------------------------------

    async def handle_reload_config(call: ServiceCall):
        target = call.data.get("host")
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "POST", "/api/v1/reload")

    # ------------------------------------------------------------
    # get_backends
    # ------------------------------------------------------------

    async def handle_get_backends(call: ServiceCall):
        target = call.data.get("host")
        results: dict[str, Any] = {}
        for coord in await _get_target_coordinators(target):
            base = getattr(coord, "_base_url", None)
            if not base:
                continue
            headers: dict[str, str] = {}
            if getattr(coord, "_api_key", None):
                headers["X-API-Key"] = coord._api_key
            url = f"{base}/api/v1/servers"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, ssl=getattr(coord, "_verify_ssl", True), timeout=10) as resp:
                        results[getattr(coord, "_name", base)] = await resp.json()
            except Exception as err:
                results[getattr(coord, "_name", base)] = {"error": str(err)}
        _LOGGER.info("dnsdist servers/backends: %s", results)

    # ------------------------------------------------------------
    # runtime_command
    # ------------------------------------------------------------

    async def handle_runtime_command(call: ServiceCall):
        target = call.data.get("host")
        command = call.data.get("command")
        if not command:
            _LOGGER.warning("runtime_command requires 'command' parameter")
            return
        for coord in await _get_target_coordinators(target):
            payload = {"command": command}
            await _call_dnsdist_api(coord, "POST", "/api/v1/console", json_data=payload)

    # ------------------------------------------------------------
    # Register all in HA
    # ------------------------------------------------------------

    hass.services.async_register(DOMAIN, "clear_cache", handle_clear_cache)
    hass.services.async_register(DOMAIN, "enable_server", handle_enable_server)
    hass.services.async_register(DOMAIN, "disable_server", handle_disable_server)
    hass.services.async_register(DOMAIN, "reload_config", handle_reload_config)
    hass.services.async_register(DOMAIN, "get_backends", handle_get_backends)
    hass.services.async_register(DOMAIN, "runtime_command", handle_runtime_command)

    _LOGGER.info(
        "Registered dnsdist services: clear_cache, enable_server, disable_server, "
        "reload_config, get_backends, runtime_command."
    )
