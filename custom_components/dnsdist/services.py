"""Service registration for PowerDNS dnsdist integration."""

from __future__ import annotations
import aiohttp
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# ============================================================
# Helper: Generic API Caller
# ============================================================

async def _call_dnsdist_api(coordinator, method: str, endpoint: str, json_data: dict | None = None) -> bool:
    """Call a dnsdist API endpoint securely."""
    base = getattr(coordinator, "_base_url", None)
    if not base:
        _LOGGER.debug("[%s] No API base URL (probably a group coordinator)", getattr(coordinator, "_name", "?"))
        return False

    headers = {}
    api_key = getattr(coordinator, "_api_key", None)
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{base}{endpoint}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, ssl=coordinator._verify_ssl, json=json_data) as resp:
                if resp.status in (200, 204):
                    _LOGGER.info("[%s] dnsdist API %s %s succeeded", coordinator._name, method, endpoint)
                    return True
                text = await resp.text()
                _LOGGER.warning("[%s] dnsdist API %s %s failed: %s %s", coordinator._name, method, endpoint, resp.status, text)
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
        if not target:
            return [c for c in coords if hasattr(c, "_host")]
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
        results = {}
        for coord in await _get_target_coordinators(target):
            base = getattr(coord, "_base_url", None)
            if not base:
                continue
            headers = {}
            if getattr(coord, "_api_key", None):
                headers["X-API-Key"] = coord._api_key
            url = f"{base}/api/v1/servers"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, ssl=coord._verify_ssl) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results[coord._name] = data
                            _LOGGER.info("[%s] Retrieved %d backends", coord._name, len(data))
                        else:
                            text = await resp.text()
                            _LOGGER.warning("[%s] Backend fetch failed: %s %s", coord._name, resp.status, text)
            except Exception as err:
                _LOGGER.error("[%s] get_backends error: %s", coord._name, err)
                results[coord._name] = {"error": str(err)}

        hass.data[DOMAIN]["last_get_backends"] = results
        return results

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
