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

"""PowerDNS dnsdist integration for Home Assistant."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.components.http import StaticPathConfig

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
    DEFAULT_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    SERVICE_CLEAR_CACHE,
    STORAGE_KEY_GROUP,
    STORAGE_KEY_HISTORY,
    STORAGE_VERSION,
)

# Pre-import the platforms so Home Assistant does not try to import them from within
# the event loop while forwarding entry setups.  Importing them here during module
# evaluation avoids the blocking `import_module` warning introduced in HA 2025.10.
from . import binary_sensor  # noqa: F401  # pylint: disable=unused-import
from . import button  # noqa: F401  # pylint: disable=unused-import
from . import sensor  # noqa: F401  # pylint: disable=unused-import
from .coordinator import DnsdistCoordinator
from .group_coordinator import DnsdistGroupCoordinator
from .services import register_dnsdist_services
from .utils import (
    async_drop_unknown_members,
    async_prune_orphaned_devices,
    async_prune_orphaned_entities,
    async_remove_retired_entities,
    async_update_group_members,
    device_identifier,
    is_group_entry,
)

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


FRONTEND_URL_BASE = "/dnsdist_static"
FRONTEND_CARD_FILENAME = "dnsdist-card.js"


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Initial setup for the dnsdist integration."""
    hass.data.setdefault(DOMAIN, {})
    async_drop_unknown_members(hass)

    # Register frontend after HA is fully started
    async def _setup_frontend(_event: Any = None) -> None:
        await _async_register_frontend(hass)

    if hass.state is CoreState.running:
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

    if _resource_mode(lovelace) != "storage":
        _LOGGER.info(
            "[dnsdist] Lovelace in YAML mode. Add resource manually: url: %s/%s, type: module",
            FRONTEND_URL_BASE,
            FRONTEND_CARD_FILENAME,
        )
        return

    await _async_register_lovelace_module(hass, lovelace)


def _resource_mode(lovelace: Any) -> str | None:
    """Return how Lovelace keeps its resources, called mode until 2026.2."""
    return getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)


async def _async_loaded_resources(lovelace: Any) -> Any:
    """Return the resource collection, loaded from disk.

    ResourceStorageCollection defers loading; async_items() returns empty on an
    unloaded collection and async_create_item() would then overwrite the
    storage file, destroying all existing Lovelace resources.
    """
    resources = lovelace.resources
    if hasattr(resources, "loaded") and not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    return resources


async def _async_unregister_lovelace_module(hass: HomeAssistant) -> None:
    """Remove the card resource, which nothing serves once the last entry is gone."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None or _resource_mode(lovelace) != "storage":
        return

    url_base = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"
    try:
        resources = await _async_loaded_resources(lovelace)
        for resource in list(resources.async_items()):
            if resource.get("url", "").split("?")[0] == url_base:
                await resources.async_delete_item(resource["id"])
                _LOGGER.info("[dnsdist] Removed the dnsdist-card Lovelace resource")
    except Exception as err:
        _LOGGER.warning("[dnsdist] Could not remove the Lovelace resource %s: %s", url_base, err)


async def _async_register_lovelace_module(hass: HomeAssistant, lovelace: Any) -> None:
    """Register the card module in Lovelace resources."""
    from homeassistant.loader import async_get_integration

    url_base = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"

    # Get integration version for cache busting
    try:
        integration = await async_get_integration(hass, DOMAIN)
        url_with_version = f"{url_base}?v={integration.version}"
    except Exception:
        url_with_version = url_base

    try:
        resources = await _async_loaded_resources(lovelace)

        # Check existing resources
        for resource in resources.async_items():
            existing_url = resource.get("url", "")
            # Check if our resource exists (with or without version)
            if existing_url.split("?")[0] == url_base:
                # Already registered, check if version update needed
                if existing_url != url_with_version:
                    _LOGGER.info("[dnsdist] Updating dnsdist-card to new version")
                    await resources.async_update_item(
                        resource["id"],
                        {"res_type": "module", "url": url_with_version},
                    )
                else:
                    _LOGGER.debug("[dnsdist] dnsdist-card already registered")
                return

        # Not registered, create new
        await resources.async_create_item({"res_type": "module", "url": url_with_version})
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

    # hass.data[DOMAIN] holds nothing but coordinators, so ask the service
    # registry whether the shared services are already there.
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_CACHE):
        await register_dnsdist_services(hass)

    data: dict[str, Any] = dict(entry.data)
    is_group = is_group_entry(entry)
    update_interval = _clamp_update_interval(data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
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

    await coordinator.async_config_entry_first_refresh()

    retired = async_remove_retired_entities(hass, entry.entry_id)
    if retired:
        _LOGGER.info("[dnsdist] Removed %d entities of retired platforms from '%s'", retired, name)

    # Drop the entities of rules, dynblocks and backends that are gone.  This
    # has to happen before the platforms start: they set up concurrently and
    # each only knows about the entities it created during this run.
    removed = async_prune_orphaned_entities(hass, entry.entry_id, coordinator.data)
    if removed:
        _LOGGER.info("[dnsdist] Removed %d orphaned entities from '%s'", removed, name)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The entities have moved to the current device by now, so whatever is left
    # empty was created under an earlier name.
    async_prune_orphaned_devices(hass, entry.entry_id, device_identifier(name, is_group))

    # Clean up dispatcher listener for group coordinators on unload
    if is_group:
        entry.async_on_unload(coordinator._unsub_dispatcher)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a dnsdist entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if isinstance(coordinator, DnsdistGroupCoordinator):
            await coordinator.async_save_totals()
        async_dispatcher_send(hass, SIGNAL_DNSDIST_RELOAD)
        _LOGGER.info("Unloaded dnsdist entry '%s'", entry.title)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete what a removed entry kept on disk, and take a host out of its groups."""
    if not is_group_entry(entry):
        async_update_group_members(hass, entry.data.get(CONF_NAME, entry.title), None)

    # The removed entry is already out of the list
    if not hass.config_entries.async_entries(DOMAIN):
        await _async_unregister_lovelace_module(hass)

    for key in (STORAGE_KEY_HISTORY, STORAGE_KEY_GROUP):
        store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{key}")
        await store.async_remove()


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry) -> bool:
    """Allow deleting a device that is no longer the entry's host or group.

    Devices are keyed on the display name, so renaming one leaves the old
    device behind.  Without this the UI offers no way to delete it.
    """
    is_group = is_group_entry(entry)
    name = entry.data.get(CONF_NAME) or entry.title
    return (DOMAIN, device_identifier(name, is_group)) not in device.identifiers


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates by reloading the entry."""

    _LOGGER.debug("[dnsdist] Reloading entry '%s' after configuration update", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries to current config version."""
    data = dict(entry.data)
    ver = entry.version or 1
    changed = False

    if ver < 4:
        ver = 4
        changed = True

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, version=ver)

    return True


def _clamp_update_interval(value: Any) -> int:
    """Keep the polling interval inside the range the flows offer.

    A value outside it, from a hand edited entry or one written before the
    range was enforced, would otherwise divide by zero working out the history
    deque size. Setup would then raise before the coordinator ever reached
    hass.data, which leaves any group listing this host waiting on it.
    """
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_UPDATE_INTERVAL

    return max(MIN_UPDATE_INTERVAL, min(interval, MAX_UPDATE_INTERVAL))


def _redact(d: dict) -> dict:
    """Redact secrets for logs."""
    if "api_key" in d:
        d["api_key"] = "***"
    return d
