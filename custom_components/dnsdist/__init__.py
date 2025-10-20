"""PowerDNS dnsdist integration for Home Assistant."""

from __future__ import annotations
import logging
from copy import deepcopy
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import Platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    PLATFORMS,
    SIGNAL_DNSDIST_RELOAD,
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_API_KEY,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_UPDATE_INTERVAL,
)
from .coordinator import DnsdistCoordinator
from .group_coordinator import DnsdistGroupCoordinator

_LOGGER = logging.getLogger(__name__)


# ============================================================
# Helper: redact secrets for logs
# ============================================================

def _redact(data: dict) -> dict:
    clean = deepcopy(data)
    if clean.get(CONF_API_KEY):
        clean[CONF_API_KEY] = "***redacted***"
    return clean


# ============================================================
# Setup
# ============================================================

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up dnsdist component (core setup, no entries)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a dnsdist host or group entry."""
    hass.data.setdefault(DOMAIN, {})

    # Register all services once, when first entry is loaded
    if "_services_registered" not in hass.data[DOMAIN]:
        await async_setup_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True
        _LOGGER.info("Registered dnsdist services (first setup).")

    data = dict(entry.data)
    is_group = bool(data.get("is_group", False) or data.get("members"))

    _LOGGER.info(
        "[dnsdist] Setting up %s '%s' (raw=%s)",
        "group" if is_group else "host",
        data.get(CONF_NAME) or entry.title,
        _redact(data),
    )

    update_interval = data.get(CONF_UPDATE_INTERVAL, 30)

    if is_group:
        members = data.get("members", []) or []
        coordinator = DnsdistGroupCoordinator(
            hass,
            name=data.get(CONF_NAME) or entry.title,
            members=members,
            update_interval=update_interval,
        )
        _LOGGER.info(
            "Initialized dnsdist GROUP '%s' with %d members: %s",
            data.get(CONF_NAME) or entry.title,
            len(members),
            ", ".join(members),
        )
    else:
        host = data.get(CONF_HOST)
        port = data.get(CONF_PORT)
        api_key = data.get(CONF_API_KEY)
        use_https = data.get(CONF_USE_HTTPS, False)
        verify_ssl = data.get(CONF_VERIFY_SSL, True)

        _LOGGER.info(
            "Setting up dnsdist HOST '%s' (%s:%s)",
            data.get(CONF_NAME) or entry.title,
            host,
            port,
        )

        coordinator = DnsdistCoordinator(
            hass,
            name=data.get(CONF_NAME) or entry.title,
            host=host,
            port=port,
            api_key=api_key,
            use_https=use_https,
            verify_ssl=verify_ssl,
            update_interval=update_interval,
        )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "[dnsdist] Initial refresh failed for '%s': %s",
            data.get(CONF_NAME) or entry.title,
            err,
        )

    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload entry when options or data are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
    async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a dnsdist entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)
        _LOGGER.info("Unloaded dnsdist entry '%s'", entry.title)
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries: if they have members but no is_group flag, add it."""
    data = dict(entry.data)
    ver = entry.version or 1
    changed = False

    if ver < 3:
        ver = 3
        changed = True

    if data.get("members") is not None and "is_group" not in data:
        data["is_group"] = True
        changed = True
        _LOGGER.info(
            "[dnsdist] Migrating entry '%s': adding is_group=True because members found",
            entry.title,
        )

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, version=ver)

    return True


# ============================================================
# Services
# ============================================================

async def _call_dnsdist_api(coordinator, method: str, endpoint: str) -> bool:
    """Generic helper to call a dnsdist API endpoint."""
    base = getattr(coordinator, "_base_url", None)
    if not base:
        _LOGGER.warning(
            "Coordinator %s has no API base URL (likely a group entry)",
            getattr(coordinator, "_name", "?"),
        )
        return False

    headers = {"X-API-Key": getattr(coordinator, "_api_key", "")} if getattr(coordinator, "_api_key", None) else {}
    url = f"{base}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, ssl=coordinator._verify_ssl) as resp:
                if resp.status in (200, 204):
                    _LOGGER.info("[%s] dnsdist API %s %s succeeded", coordinator._name, method, endpoint)
                    return True
                text = await resp.text()
                _LOGGER.warning(
                    "[%s] dnsdist API %s %s failed: %s %s",
                    coordinator._name,
                    method,
                    endpoint,
                    resp.status,
                    text,
                )
    except Exception as err:
        _LOGGER.error("[%s] dnsdist API call error: %s", coordinator._name, err)
    return False


async def async_setup_services(hass: HomeAssistant):
    """Register dnsdist control and admin services."""

    async def _get_target_coordinators(target: str | None):
        """Return coordinators matching a given host name or all."""
        coords = list(hass.data.get(DOMAIN, {}).values())
        if not target:
            return [c for c in coords if hasattr(c, "_host")]
        return [c for c in coords if getattr(c, "_name", None) == target]

    # --- Basic API control commands ---

    async def handle_clear_cache(call: ServiceCall):
        target = call.data.get("host")
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "POST", "/api/v1/clearCache")

    async def handle_enable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target or not backend:
            _LOGGER.warning("enable_server requires both host and backend")
            return
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{backend}/enable")

    async def handle_disable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target or not backend:
            _LOGGER.warning("disable_server requires both host and backend")
            return
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{backend}/disable")

    async def handle_reload_config(call: ServiceCall):
        target = call.data.get("host")
        for coord in await _get_target_coordinators(target):
            await _call_dnsdist_api(coord, "POST", "/api/v1/reload")

    # --- Advanced admin services ---

    async def handle_get_backends(call: ServiceCall):
        target = call.data.get("host")
        results = {}
        for coord in await _get_target_coordinators(target):
            base = getattr(coord, "_base_url", None)
            if not base:
                continue
            headers = {"X-API-Key": getattr(coord, "_api_key", "")} if getattr(coord, "_api_key", None) else {}
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

    async def handle_runtime_command(call: ServiceCall):
        target = call.data.get("host")
        command = call.data.get("command")
        if not command:
            _LOGGER.warning("runtime_command requires 'command' parameter")
            return
        for coord in await _get_target_coordinators(target):
            payload = {"command": command}
            headers = {"X-API-Key": getattr(coord, "_api_key", "")} if getattr(coord, "_api_key", None) else {}
            url = f"{coord._base_url}/api/v1/console"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, ssl=coord._verify_ssl) as resp:
                        text = await resp.text()
                        if resp.status in (200, 204):
                            _LOGGER.info("[%s] Executed runtime command: %s", coord._name, command)
                        else:
                            _LOGGER.warning("[%s] Command failed (%s): %s", coord._name, resp.status, text)
            except Exception as err:
                _LOGGER.error("[%s] runtime_command error: %s", coord._name, err)

    # --- Register all services ---

    hass.services.async_register(DOMAIN, "clear_cache", handle_clear_cache)
    hass.services.async_register(DOMAIN, "enable_server", handle_enable_server)
    hass.services.async_register(DOMAIN, "disable_server", handle_disable_server)
    hass.services.async_register(DOMAIN, "reload_config", handle_reload_config)
    hass.services.async_register(DOMAIN, "get_backends", handle_get_backends)
    hass.services.async_register(DOMAIN, "runtime_command", handle_runtime_command)

    _LOGGER.info(
        "Registered dnsdist control services: clear_cache, enable_server, disable_server, "
        "reload_config, get_backends, runtime_command."
    )
