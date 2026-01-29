"""PowerDNS dnsdist integration for Home Assistant."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, CoreState, callback
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.components.http import StaticPathConfig

from .const import (
    DOMAIN,
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
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


FRONTEND_URL_BASE = "/dnsdist_static"
FRONTEND_CARD_FILENAME = "dnsdist-card.js"


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Initial setup for the dnsdist integration."""
    hass.data.setdefault(DOMAIN, {})

    # Register frontend after HA is fully started
    async def _setup_frontend(_event: Any = None) -> None:
        await _async_register_frontend(hass)

    if hass.state == CoreState.running:
        await _setup_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _setup_frontend)

    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the dnsdist Lovelace card as a frontend resource."""
    www_path = Path(__file__).parent / "www"
    card_path = www_path / FRONTEND_CARD_FILENAME

    if not card_path.exists():
        _LOGGER.warning(
            "[dnsdist] Frontend card not found at %s, card will not be available",
            card_path,
        )
        return

    # Register static path for serving files from www/
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL_BASE, str(www_path), cache_headers=False)]
        )
        _LOGGER.debug("[dnsdist] Registered static path: %s -> %s", FRONTEND_URL_BASE, www_path)
    except RuntimeError:
        _LOGGER.debug("[dnsdist] Static path already registered: %s", FRONTEND_URL_BASE)

    # Register as Lovelace resource
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.warning("[dnsdist] Lovelace not available, cannot register card resource")
        return

    if lovelace.mode != "storage":
        _LOGGER.info(
            "[dnsdist] Lovelace in YAML mode. Add resource manually: "
            "url: %s/%s, type: module",
            FRONTEND_URL_BASE,
            FRONTEND_CARD_FILENAME,
        )
        return

    # Wait for lovelace resources to be loaded
    await _async_register_lovelace_module(hass, lovelace)


async def _async_register_lovelace_module(hass: HomeAssistant, lovelace: Any) -> None:
    """Register the card module in Lovelace resources."""
    from homeassistant.loader import async_get_integration

    # Get integration version for cache busting
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version
    except Exception:
        version = "1.2.1"

    url_with_version = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={version}"
    url_base = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"

    @callback
    def _check_resources_loaded(_now: Any = None) -> None:
        """Check if resources are loaded and register."""
        if not lovelace.resources.loaded:
            _LOGGER.debug("[dnsdist] Lovelace resources not loaded yet, retrying...")
            async_call_later(hass, 5, _check_resources_loaded)
            return

        hass.async_create_task(_do_register_module(lovelace, url_base, url_with_version))

    _check_resources_loaded()


async def _do_register_module(lovelace: Any, url_base: str, url_with_version: str) -> None:
    """Actually register or update the module."""
    try:
        # Check existing resources
        for resource in lovelace.resources.async_items():
            existing_url = resource.get("url", "")
            # Check if our resource exists (with or without version)
            if existing_url.split("?")[0] == url_base:
                # Already registered, check if version update needed
                if existing_url != url_with_version:
                    _LOGGER.info("[dnsdist] Updating dnsdist-card to new version")
                    await lovelace.resources.async_update_item(
                        resource["id"],
                        {"res_type": "module", "url": url_with_version},
                    )
                else:
                    _LOGGER.debug("[dnsdist] dnsdist-card already registered")
                return

        # Not registered, create new
        await lovelace.resources.async_create_item(
            {"res_type": "module", "url": url_with_version}
        )
        _LOGGER.info("[dnsdist] Registered dnsdist-card as Lovelace resource")

    except Exception as err:
        _LOGGER.warning(
            "[dnsdist] Could not register Lovelace resource: %s. "
            "Add manually: Settings > Dashboards > Resources > Add '%s' as JavaScript Module",
            err,
            url_with_version,
        )


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
            api_key = data[CONF_API_KEY]
            entry.add_secret(CONF_API_KEY, api_key)
            data[CONF_API_KEY] = None
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


def _redact(d: dict) -> dict:
    """Redact secrets for logs."""
    if "api_key" in d:
        d["api_key"] = "***"
    return d
