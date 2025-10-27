# 202510231625
"""Service registration for PowerDNS dnsdist integration (REST-only)."""

from __future__ import annotations

import logging
from urllib.parse import urlencode, quote

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _call_dnsdist_api(
    coordinator,
    method: str,
    endpoint: str,
    *,
    params: dict | None = None,
    json_data: dict | None = None,
) -> tuple[int, str]:
    """Generic caller against the dnsdist HTTP API for a single coordinator."""
    base = getattr(coordinator, "_base_url", None)
    if not base:
        return 0, "no-base-url"

    headers = {}
    api_key = getattr(coordinator, "_api_key", None)
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{base}{endpoint}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    session = async_get_clientsession(coordinator.hass)

    try:
        async with session.request(
            method, url, headers=headers, ssl=getattr(coordinator, "_verify_ssl", True), json=json_data
        ) as resp:
            text = await resp.text()
            if resp.status in (200, 204):
                _LOGGER.info("[%s] %s %s OK", getattr(coordinator, "_name", "?"), method, endpoint)
            else:
                _LOGGER.warning(
                    "[%s] dnsdist API %s %s failed: %s %s",
                    getattr(coordinator, "_name", "?"),
                    method,
                    endpoint,
                    resp.status,
                    text,
                )
            return resp.status, text
    except Exception as err:
        _LOGGER.error(
            "[%s] dnsdist API call error on %s %s: %s",
            getattr(coordinator, "_name", "?"),
            method,
            endpoint,
            err,
        )
        return -1, str(err)


async def register_dnsdist_services(hass: HomeAssistant):
    """Register REST-only dnsdist services."""

    async def _targets(target: str | None):
        coords = list(hass.data.get(DOMAIN, {}).values())
        if not target:
            # Only real hosts (exclude group coordinators that don't have _host)
            return [c for c in coords if hasattr(c, "_host")]
        return [c for c in coords if getattr(c, "_name", None) == target]

    # ------------------------------------------------------------
    # clear_cache (REST): DELETE /api/v1/cache?pool=<pool>&name=.&suffix=1
    # ------------------------------------------------------------
    async def handle_clear_cache(call: ServiceCall):
        pool = call.data.get("pool", "")
        target = call.data.get("host")
        for coord in await _targets(target):
            status, _ = await _call_dnsdist_api(
                coord,
                "DELETE",
                "/api/v1/cache",
                params={"pool": pool, "name": ".", "suffix": 1},
            )
            if status in (200, 204):
                _LOGGER.info(
                    "[%s] Cleared packet cache on pool '%s' via REST",
                    getattr(coord, "_name", "?"),
                    pool,
                )
            else:
                _LOGGER.warning(
                    "[%s] Cache clear failed on pool '%s' (HTTP %s)",
                    getattr(coord, "_name", "?"),
                    pool,
                    status,
                )

    # ------------------------------------------------------------
    # enable_server (REST): PUT /api/v1/servers/{backend}/enable
    # ------------------------------------------------------------
    async def handle_enable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target:
            _LOGGER.warning("enable_server requires a 'host'")
            return

        encoded_backend = _encode_backend_segment(backend)
        if not encoded_backend:
            _LOGGER.warning("enable_server received an invalid backend identifier")
            return
        for coord in await _targets(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{encoded_backend}/enable")

    # ------------------------------------------------------------
    # disable_server (REST): PUT /api/v1/servers/{backend}/disable
    # ------------------------------------------------------------
    async def handle_disable_server(call: ServiceCall):
        target = call.data.get("host")
        backend = call.data.get("backend")
        if not target:
            _LOGGER.warning("disable_server requires a 'host'")
            return

        encoded_backend = _encode_backend_segment(backend)
        if not encoded_backend:
            _LOGGER.warning("disable_server received an invalid backend identifier")
            return
        for coord in await _targets(target):
            await _call_dnsdist_api(coord, "PUT", f"/api/v1/servers/{encoded_backend}/disable")

    # ------------------------------------------------------------
    # get_backends (REST): GET /api/v1/servers
    # ------------------------------------------------------------
    async def handle_get_backends(call: ServiceCall):
        target = call.data.get("host")
        for coord in await _targets(target):
            await _call_dnsdist_api(coord, "GET", "/api/v1/servers")

    # Register REST-only services
    hass.services.async_register(DOMAIN, "clear_cache", handle_clear_cache)
    hass.services.async_register(DOMAIN, "enable_server", handle_enable_server)
    hass.services.async_register(DOMAIN, "disable_server", handle_disable_server)
    hass.services.async_register(DOMAIN, "get_backends", handle_get_backends)

    _LOGGER.info(
        "Registered dnsdist services: clear_cache, enable_server, disable_server, get_backends."
    )


def _encode_backend_segment(raw_backend: str | None) -> str | None:
    """Return a safely encoded backend identifier for URL paths."""

    if raw_backend is None:
        return None

    if not isinstance(raw_backend, str):
        _LOGGER.warning("Received non-string backend identifier: %s", raw_backend)
        return None

    backend = raw_backend.strip()
    if not backend:
        return None

    # Reject control characters outright to avoid header injection or log confusion
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in backend):
        _LOGGER.warning("Backend identifier contains control characters and was rejected")
        return None

    # Percent-encode the backend to keep it as a single URL segment.
    return quote(backend, safe="")
