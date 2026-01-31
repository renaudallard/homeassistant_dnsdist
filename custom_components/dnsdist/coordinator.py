"""Coordinator for PowerDNS dnsdist hosts."""

from __future__ import annotations

import logging
import time
from asyncio import timeout
from time import monotonic
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Tuple

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_CPU,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_DYNAMIC_RULES,
    ATTR_FILTERING_RULES,
    ATTR_QUERIES,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    DOMAIN,
    SECURITY_STATUS_MAP,
    STORAGE_KEY_HISTORY,
    STORAGE_VERSION,
)
from .utils import HistoryMixin, coerce_int, make_zero_data, slugify_rule

_LOGGER = logging.getLogger(__name__)


class DnsdistCoordinator(HistoryMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls a single dnsdist host."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        name: str,
        host: str,
        port: int,
        api_key: str | None,
        use_https: bool,
        verify_ssl: bool,
        update_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"dnsdist_{name}",
            update_interval=timedelta(seconds=update_interval),
        )
        self._name = name
        self._entry_id = entry_id
        self._host = host
        self._port = port
        self._api_key = api_key
        self._use_https = use_https
        self._verify_ssl = verify_ssl
        self._base_url = f"{'https' if use_https else 'http'}://{host}:{port}"
        # Track CPU deltas
        self._last_cpu_user_msec: int | None = None
        self._last_update_ts: float | None = None
        # Rolling history of (wallclock_ts, queries_counter) for rate sensors
        self._history: Deque[Tuple[float, int]] = deque()  # seconds since epoch, queries
        self._history_dirty = False
        self._last_history_persist: float | None = None
        self._history_store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_{STORAGE_KEY_HISTORY}",
        )
        self._history_loaded = False
        # Avoid hammering unsupported filtering rules endpoint with 404s
        self._filtering_rules_supported: bool | None = None
        self._dynamic_rules_supported: bool | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize dnsdist stats."""
        await self._async_ensure_history_loaded()

        url = f"{self._base_url}/api/v1/servers/localhost/statistics"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}

        session = async_get_clientsession(self.hass)

        try:
            ssl_context = False if not self._verify_ssl else None
            _LOGGER.debug("[%s] Requesting stats from %s (ssl=%s)", self._name, url, ssl_context)
            async with timeout(10):
                async with session.get(url, headers=headers, ssl=ssl_context) as resp:
                    if resp.status != 200:
                        raise ConnectionError(f"HTTP {resp.status}")
                    stats = await resp.json()
        except aiohttp.ClientSSLError as err:
            _LOGGER.warning("[%s] SSL error: %s", self._name, err)
            data = dict(self.data or self._zero_data())
            return data
        except aiohttp.ClientConnectorError as err:
            _LOGGER.warning("[%s] Connection failed: %s", self._name, err)
            data = dict(self.data or self._zero_data())
            return data
        except Exception as err:
            _LOGGER.warning("[%s] Fetch error: %s", self._name, err)
            # Preserve last data to avoid sensor going unavailable
            data = dict(self.data or self._zero_data())
            return data

        stats_preview = stats[:10] if isinstance(stats, list) else stats
        _LOGGER.debug("[%s] Raw dnsdist stats (first 10): %s", self._name, stats_preview)

        normalized = self._normalize(stats)

        # Preserve the latest known filtering rules so sensors remain available when
        # the endpoint temporarily fails or is disabled. ``self.data`` is ``None``
        # during the first refresh, so guard every lookup carefully.
        previous_rules: dict[str, Any] | None = None
        if isinstance(self.data, dict):
            maybe_rules = self.data.get(ATTR_FILTERING_RULES)
            if isinstance(maybe_rules, dict):
                previous_rules = maybe_rules

        if previous_rules is not None and ATTR_FILTERING_RULES not in normalized:
            normalized[ATTR_FILTERING_RULES] = previous_rules

        # Preserve dynamic rules similarly
        previous_dynamic: dict[str, Any] | None = None
        if isinstance(self.data, dict):
            maybe_dynamic = self.data.get(ATTR_DYNAMIC_RULES)
            if isinstance(maybe_dynamic, dict):
                previous_dynamic = maybe_dynamic

        if previous_dynamic is not None and ATTR_DYNAMIC_RULES not in normalized:
            normalized[ATTR_DYNAMIC_RULES] = previous_dynamic

        # --- Compute CPU % based on cpu-user-msec counter ---
        try:
            cpu_user_msec = normalized.get("cpu_user_msec")
            now_mono = monotonic()
            if isinstance(cpu_user_msec, (int, float)):
                if self._last_cpu_user_msec is not None and self._last_update_ts is not None:
                    delta_cpu = cpu_user_msec - self._last_cpu_user_msec
                    delta_time = now_mono - self._last_update_ts
                    if delta_time > 0 and delta_cpu >= 0:
                        cpu_percent = ((delta_cpu / 1000.0) / delta_time) * 100
                        normalized[ATTR_CPU] = round(max(0.0, min(cpu_percent, 100.0)), 2)
                self._last_cpu_user_msec = int(cpu_user_msec)
                self._last_update_ts = now_mono
        except Exception as err:
            _LOGGER.debug("[%s] CPU computation failed: %s", self._name, err)

        # --- Compute rolling-window request rates ---
        try:
            now_ts = time.time()
            q = int(normalized.get(ATTR_QUERIES, 0))
            self._update_history(now_ts, q)
            req_hour, req_day = self._compute_rates(now_ts, q)
            normalized[ATTR_REQ_PER_HOUR] = req_hour
            normalized[ATTR_REQ_PER_DAY] = req_day
        except Exception as err:
            _LOGGER.debug("[%s] Rate computation failed: %s", self._name, err)

        await self._async_save_history()

        try:
            rules = await self._async_fetch_filtering_rules(session, headers)
            if rules is not None:
                normalized[ATTR_FILTERING_RULES] = rules
        except Exception as err:
            _LOGGER.debug("[%s] Filtering rules fetch failed: %s", self._name, err)

        try:
            dynamic_rules = await self._async_fetch_dynamic_rules(session, headers)
            if dynamic_rules is not None:
                normalized[ATTR_DYNAMIC_RULES] = dynamic_rules
        except Exception as err:
            _LOGGER.debug("[%s] Dynamic rules fetch failed: %s", self._name, err)

        return normalized

    def _zero_data(self) -> dict[str, Any]:
        data = make_zero_data()
        data["cpu_user_msec"] = 0  # Host-specific field for CPU calculation
        return data

    def _normalize(self, stats: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """Normalize dnsdist JSON stats into HA-friendly keys."""
        normalized: dict[str, Any] = self._zero_data()

        try:
            items = stats if isinstance(stats, list) else stats.get("statistics", [])
            for item in items:
                key = item.get("name")
                val = item.get("value")

                if key == "queries":
                    normalized[ATTR_QUERIES] = int(val)
                elif key == "responses":
                    normalized[ATTR_RESPONSES] = int(val)
                elif key == "drops":
                    normalized[ATTR_DROPS] = int(val)
                elif key in ("rule-drop", "rule_drop"):
                    normalized[ATTR_RULE_DROP] = int(val)
                elif key in ("downstream-send-errors", "downstream_errors"):
                    normalized[ATTR_DOWNSTREAM_ERRORS] = int(val)
                elif key in ("cache-hits", "cache_hits"):
                    normalized[ATTR_CACHE_HITS] = int(val)
                elif key in ("cache-misses", "cache_misses"):
                    normalized[ATTR_CACHE_MISSES] = int(val)
                elif key in ("uptime",):
                    normalized[ATTR_UPTIME] = int(val)
                elif key in ("cpu-user-msec", "cpu_user_msec"):
                    normalized["cpu_user_msec"] = int(val)
                elif key in ("security-status", "security_status"):
                    sec = int(val)
                    normalized[ATTR_SECURITY_STATUS] = SECURITY_STATUS_MAP.get(sec, "unknown")

            # Compute cache hit %
            hits = normalized[ATTR_CACHE_HITS]
            misses = normalized[ATTR_CACHE_MISSES]
            denom = hits + misses
            if denom > 0:
                normalized[ATTR_CACHE_HITRATE] = round((hits / denom) * 100, 2)
        except Exception as err:
            _LOGGER.warning("[%s] Failed to normalize data: %s", self._name, err)

        return normalized

    async def _async_fetch_filtering_rules(
        self, session: aiohttp.ClientSession, headers: dict[str, str]
    ) -> dict[str, dict[str, Any]] | None:
        """Fetch filtering rules and normalize them into a mapping."""

        if self._filtering_rules_supported is False:
            return None

        url = f"{self._base_url}/api/v1/servers/localhost"
        payload: Any | None = None

        try:
            ssl_context = False if not self._verify_ssl else None
            _LOGGER.debug("[%s] Requesting filtering rules from %s (ssl=%s)", self._name, url, ssl_context)
            async with timeout(10):
                async with session.get(url, headers=headers, ssl=ssl_context) as resp:
                    if resp.status == 404:
                        if self._filtering_rules_supported is not False:
                            _LOGGER.debug(
                                "[%s] Filtering rules endpoint not available (404)",
                                self._name,
                            )
                        self._filtering_rules_supported = False
                        return None
                    if resp.status != 200:
                        raise ConnectionError(f"HTTP {resp.status}")
                    payload = await resp.json()
        except Exception as err:
            _LOGGER.debug("[%s] Could not retrieve filtering rules: %s", self._name, err)
            return None

        if payload is None:
            return None

        self._filtering_rules_supported = True

        rules_raw: list[dict[str, Any]] = []
        if isinstance(payload, list):
            rules_raw = payload
        elif isinstance(payload, dict):
            # ``rules`` is the documented list of live filtering rules. Allow a few
            # variations to support older or vendor-modified responses.
            candidate_values: tuple[Any, ...] = (
                payload.get("rules"),
                payload.get("filteringRules"),
                payload.get("filtering_rules"),
            )
            for candidate in candidate_values:
                if isinstance(candidate, list):
                    rules_raw = candidate
                    break
                if isinstance(candidate, dict):
                    for nested_key in ("rules", "filteringRules", "data"):
                        maybe = candidate.get(nested_key)
                        if isinstance(maybe, list):
                            rules_raw = maybe
                            break
                    if rules_raw:
                        break

        rules: dict[str, dict[str, Any]] = {}
        for item in rules_raw:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_filtering_rule(item)
            if normalized is None:
                continue
            slug = normalized.pop("slug")
            rules[slug] = normalized

        return rules

    def _normalize_filtering_rule(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a filtering rule entry."""
        name = str(item.get("name") or item.get("rule") or item.get("uuid") or item.get("id") or "Unnamed Rule").strip()
        if not name:
            name = "Unnamed Rule"

        matches = 0
        for key in ("matches", "numMatches", "hits", "num_hits", "hitCount", "count"):
            if key in item:
                matches = coerce_int(item.get(key))
                break

        slug_source = item.get("uuid") or item.get("id") or name
        slug = slugify_rule(slug_source)

        rule = {
            "slug": slug,
            "name": name,
            "matches": matches,
            "id": item.get("id"),
            "uuid": item.get("uuid"),
            "action": item.get("action"),
            "rule": item.get("rule"),
            "type": item.get("type"),
            "enabled": item.get("enabled"),
            "bypass": item.get("bypass"),
        }

        return rule

    async def _async_fetch_dynamic_rules(
        self, session: aiohttp.ClientSession, headers: dict[str, str]
    ) -> dict[str, dict[str, Any]] | None:
        """Fetch dynamic rules (dynblocks) and normalize them into a mapping."""

        if self._dynamic_rules_supported is False:
            return None

        # dnsdist exposes dynblocks via /jsonstat?command=dynblocklist
        url = f"{self._base_url}/jsonstat?command=dynblocklist"
        payload: Any | None = None

        try:
            ssl_context = False if not self._verify_ssl else None
            _LOGGER.debug("[%s] Requesting dynamic rules from %s", self._name, url)
            async with timeout(10):
                async with session.get(url, headers=headers, ssl=ssl_context) as resp:
                    if resp.status == 404:
                        if self._dynamic_rules_supported is not False:
                            _LOGGER.debug(
                                "[%s] Dynamic rules endpoint not available (404)",
                                self._name,
                            )
                        self._dynamic_rules_supported = False
                        return None
                    if resp.status != 200:
                        raise ConnectionError(f"HTTP {resp.status}")
                    payload = await resp.json()
        except Exception as err:
            _LOGGER.debug("[%s] Could not retrieve dynamic rules: %s", self._name, err)
            return None

        if payload is None:
            return None

        self._dynamic_rules_supported = True

        # Response format: {"127.0.0.1/32": {"blocks": 3, "reason": "...", "seconds": 10}, ...}
        dynblocks_raw: dict[str, Any] = {}
        if isinstance(payload, dict):
            # The response is directly a dict keyed by network
            dynblocks_raw = payload

        if not dynblocks_raw:
            return {}

        rules: dict[str, dict[str, Any]] = {}
        for key, item in dynblocks_raw.items():
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_dynamic_rule(key, item)
            if normalized is None:
                continue
            slug = normalized.pop("slug")
            rules[slug] = normalized

        return rules

    def _normalize_dynamic_rule(self, key: str, item: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a dynamic rule (dynblock) entry."""
        # The key is typically the network/client being blocked (e.g., "192.168.1.0/24")
        network = str(key).strip()
        if not network:
            return None

        slug = slugify_rule(network)

        # Extract block count from various possible field names
        blocks = 0
        for field in ("blocks", "count", "hits", "nmBlocks"):
            if field in item:
                blocks = coerce_int(item.get(field))
                break

        # Extract remaining seconds
        seconds = coerce_int(item.get("seconds", 0))

        rule = {
            "slug": slug,
            "network": network,
            "reason": item.get("reason") or item.get("message") or "Unknown",
            "action": item.get("action") or "refused",
            "blocks": blocks,
            "seconds": seconds,
            "ebpf": item.get("ebpf", False),
            "warning": item.get("warning", False),
        }

        return rule
