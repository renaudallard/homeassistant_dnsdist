"""PowerDNS dnsdist integration for Home Assistant."""

from __future__ import annotations
import logging
from copy import deepcopy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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


def _redact(data: dict) -> dict:
    clean = deepcopy(data)
    if clean.get(CONF_API_KEY):
        clean[CONF_API_KEY] = "***redacted***"
    return clean


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up dnsdist component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a dnsdist host or group entry."""
    data = dict(entry.data)
    # Robust group detection: respect flag OR presence of members list
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
            hass, name=data.get(CONF_NAME) or entry.title, members=members, update_interval=update_interval
        )
        _LOGGER.info("Initialized dnsdist GROUP '%s' with %d members: %s",
                     data.get(CONF_NAME) or entry.title, len(members), ", ".join(members))
    else:
        host = data.get(CONF_HOST)
        port = data.get(CONF_PORT)
        api_key = data.get(CONF_API_KEY)
        use_https = data.get(CONF_USE_HTTPS, False)
        verify_ssl = data.get(CONF_VERIFY_SSL, True)

        _LOGGER.info("Setting up dnsdist HOST '%s' (%s:%s)", data.get(CONF_NAME) or entry.title, host, port)

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
        _LOGGER.warning("[dnsdist] Initial refresh failed for '%s': %s",
                        data.get(CONF_NAME) or entry.title, err)

    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    # Notify groups when anything changes
    async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)

    # Reload on options updates
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

    # Upgrade to v3 baseline
    if ver < 3:
        ver = 3
        changed = True

    # If "members" present but missing "is_group", fix it
    if data.get("members") is not None and "is_group" not in data:
        data["is_group"] = True
        changed = True
        _LOGGER.info("[dnsdist] Migrating entry '%s': adding is_group=True because members found", entry.title)

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, version=ver)

    return True
