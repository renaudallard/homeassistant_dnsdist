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

"""Service registration for PowerDNS dnsdist integration (REST-only)."""

from __future__ import annotations

import logging
from asyncio import timeout
from typing import Any
from urllib.parse import urlencode

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, SERVICE_CLEAR_CACHE
from .utils import slugify_rule

_LOGGER = logging.getLogger(__name__)


async def _call_dnsdist_api(
    coordinator,
    method: str,
    endpoint: str,
    *,
    params: dict | None = None,
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
        verify_ssl = getattr(coordinator, "_verify_ssl", True)
        ssl_context = False if not verify_ssl else None
        async with timeout(10):
            async with session.request(method, url, headers=headers, ssl=ssl_context) as resp:
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
    except TimeoutError:
        _LOGGER.warning(
            "[%s] dnsdist API call timed out on %s %s",
            getattr(coordinator, "_name", "?"),
            method,
            endpoint,
        )
        return -1, "timeout"
    except Exception as err:
        _LOGGER.error(
            "[%s] dnsdist API call error on %s %s: %s",
            getattr(coordinator, "_name", "?"),
            method,
            endpoint,
            err,
        )
        return -1, str(err)


def _host_targets(hass: HomeAssistant, target: str | None) -> list[Any]:
    """Pick the host coordinators a service call is aimed at.

    A group has no API of its own, so it is never a target: its Clear Cache
    button fans out over the member names instead. The name is matched exactly
    first and then by slug, so the entity ID spelling the card and the entity
    registry use finds the host as well as the display name does.
    """
    hosts = [coord for coord in hass.data.get(DOMAIN, {}).values() if hasattr(coord, "_host")]
    if not target:
        return hosts

    if exact := [coord for coord in hosts if coord._name == target]:
        return exact

    wanted = slugify_rule(target)
    return [coord for coord in hosts if slugify_rule(coord._name) == wanted]


async def register_dnsdist_services(hass: HomeAssistant):
    """Register REST-only dnsdist services."""

    # ------------------------------------------------------------
    # clear_cache (REST): DELETE /api/v1/cache?pool=<pool>&name=.&suffix=1
    # ------------------------------------------------------------
    async def handle_clear_cache(call: ServiceCall):
        pool = call.data.get("pool", "")
        target = call.data.get("host")

        coords = _host_targets(hass, target)
        if not coords:
            # Saying nothing at all looks exactly like a cache that was cleared.
            if target:
                _LOGGER.warning("[dnsdist] clear_cache found no host called '%s'", target)
            else:
                _LOGGER.warning("[dnsdist] clear_cache found no dnsdist hosts to clear")
            return

        for coord in coords:
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

    # Register REST-only services
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_CACHE, handle_clear_cache)

    _LOGGER.info("Registered dnsdist service: %s.", SERVICE_CLEAR_CACHE)
