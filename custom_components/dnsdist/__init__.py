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
from .services import register_dnsdist_services

_LOGGER = logging.getLogger(__name__)


# ============================================================
# Utility: redact secrets in logs
# ============================================================

def _redact(data: dict) -> dict:
    clean = deepcopy(data)
    if CONF_API_KEY in clean:
        clean[CONF_API_KEY] = "***secret***"
    return clean


# ============================================================
# Component setup
# ============================================================

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initial setup for the dnsdist integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a dnsdist host or group entry."""
    hass.data.setdefault(DOMAIN, {})

    # Register all services once (on first entry load)
    if "_services_registered" not in hass.data[DOMAIN]:
        await register_dnsdist_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True
        _LOGGER.info("[dnsdist] Registered control services.")

    data = dict(entry.data)
    is_group = bool(data.get("is_group", False) or data.get("members"))
    update_interval = data.get(CONF_UPDATE_INTERVAL, 30)

    name = data.get(CONF_NAME) or entry.title
    _LOGGER.info(
        "[dnsdist] Setting up %s '%s' (raw=%s)",
        "group" if is_group else "host",
        name,
        _redact(data),
    )

    # ------------------------------------------------------------
    # Create coordinator
    # ------------------------------------------------------------
    if is_group:
        members = data.get("members", []) or []
        coordinator = DnsdistGroupCoordinator(
            hass, name=name, members=members, update_interval=update_interval
        )
    else:
        host = data.get(CONF_HOST)
        port = data.get(CONF_PORT)
        use_https = data.get(CONF_USE_HTTPS, False)
        verify_ssl = data.get(CONF_VERIFY_SSL, True)
        api_key = None

        # Securely retrieve API key (if stored as secret)
        try:
            api_key = await entry.async_get_secret(CONF_API_KEY)
        except AttributeError:
            # For HA versions before secure secret API
            api_key = data.get(CONF_API_KEY)

        coordinator = DnsdistCoordinator(
            hass,
            name=name,
            host=host,
            port=port,
            api_key=api_key,
            use_https=use_https,
            verify_ssl=verify_ssl,
            update_interval=update_interval,
        )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Perform first data refresh
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("[dnsdist] Initial refresh failed for '%s': %s", name, err)

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


# ============================================================
# Entry lifecycle management
# ============================================================

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload a dnsdist entry when options or data change."""
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


# ============================================================
# Migration to secure storage
# ============================================================

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries to new format with secure secret storage."""
    data = dict(entry.data)
    ver = entry.version or 1
    changed = False

    # Upgrade baseline version
    if ver < 4:
        ver = 4
        changed = True

    # Move plaintext API key to HA secret store if possible
    if data.get(CONF_API_KEY):
        try:
            hass.loop.create_task(entry.async_set_secret(CONF_API_KEY, data.pop(CONF_API_KEY)))
            _LOGGER.info("[dnsdist] Migrated API key for '%s' to secure storage", entry.title)
            changed = True
        except AttributeError:
            _LOGGER.warning(
                "[dnsdist] Secure secret API not available; keeping plaintext API key for '%s'.",
                entry.title,
            )
        except Exception as err:
            _LOGGER.warning("[dnsdist] Could not migrate API key for '%s': %s", entry.title, err)

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, version=ver)

    return True
