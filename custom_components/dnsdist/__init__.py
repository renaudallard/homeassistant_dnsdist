# 202510231445
"""PowerDNS dnsdist integration for Home Assistant."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    CONF_MEMBERS,
    CONF_IS_GROUP,
    DEFAULT_UPDATE_INTERVAL,
)

# Pre-import the platforms so Home Assistant does not try to import them from within
# the event loop while forwarding entry setups.  Importing them here during module
# evaluation avoids the blocking `import_module` warning introduced in HA 2025.10.
from . import button  # noqa: F401  # pylint: disable=unused-import
from . import sensor  # noqa: F401  # pylint: disable=unused-import
from .coordinator import DnsdistCoordinator
from .group_coordinator import DnsdistGroupCoordinator
from .services import register_dnsdist_services

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Initial setup for the dnsdist integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a dnsdist host or group entry."""
    hass.data.setdefault(DOMAIN, {})

    if "_services_registered" not in hass.data[DOMAIN]:
        await register_dnsdist_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True
        _LOGGER.info("[dnsdist] Registered control services.")

    data: dict[str, Any] = dict(entry.data)
    is_group = bool(data.get(CONF_IS_GROUP, False) or data.get(CONF_MEMBERS))
    update_interval = int(data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    name = data.get(CONF_NAME) or entry.title

    _LOGGER.info(
        "[dnsdist] Setting up %s '%s' (raw=%s)",
        "group" if is_group else "host",
        name,
        _redact(deepcopy(data)),
    )

    if is_group:
        members = list(data.get(CONF_MEMBERS, []))
        coordinator = DnsdistGroupCoordinator(
            hass,
            entry_id=entry.entry_id,
            name=name,
            members=members,
            update_interval=update_interval,
        )
    else:
        host = data.get(CONF_HOST)
        port = int(data.get(CONF_PORT, 8083))
        use_https = bool(data.get(CONF_USE_HTTPS, False))
        verify_ssl = bool(data.get(CONF_VERIFY_SSL, True))

        api_key: str | None = None
        try:
            api_key = await entry.async_get_secret(CONF_API_KEY)
        except AttributeError:
            api_key = data.get(CONF_API_KEY)

        coordinator = DnsdistCoordinator(
            hass,
            entry_id=entry.entry_id,
            name=name,
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
        _LOGGER.warning("[dnsdist] Initial refresh failed for '%s': %s", name, err)

    # Forward platforms (now includes BUTTON)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.BUTTON])

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a dnsdist entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.BUTTON])
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)
        _LOGGER.info("Unloaded dnsdist entry '%s'", entry.title)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates by reloading the entry."""

    _LOGGER.debug("[dnsdist] Reloading entry '%s' after configuration update", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries to new format with secure secret storage."""
    data = dict(entry.data)
    ver = entry.version or 1
    changed = False

    if ver < 4:
        ver = 4
        changed = True

    if data.get(CONF_API_KEY):
        try:
            hass.config_entries.async_update_entry(entry, data={**data, CONF_API_KEY: None})
            entry.add_secret(CONF_API_KEY, data[CONF_API_KEY])
            _LOGGER.info("[dnsdist] Migrated API key for '%s' to secure storage", entry.title)
            changed = True
        except AttributeError:
            _LOGGER.warning("[dnsdist] Secure secret API not available; keeping plaintext API key for '%s'.", entry.title)
        except Exception as err:
            _LOGGER.warning("[dnsdist] Could not migrate API key for '%s': %s", entry.title, err)

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, version=ver)

    return True


def _redact(d: dict) -> dict:
    """Redact secrets for logs."""
    if "api_key" in d:
        d["api_key"] = "***"
    return d
