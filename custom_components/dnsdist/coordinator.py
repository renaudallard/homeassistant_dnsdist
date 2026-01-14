"""Coordinator for PowerDNS dnsdist hosts."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from datetime import timedelta
from itertools import islice
from asyncio import timeout
from time import monotonic
from typing import Any, Deque, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
    ATTR_FILTERING_RULES,
    STORAGE_VERSION,
    STORAGE_KEY_HISTORY,
)

_LOGGER = logging.getLogger(__name__)


class DnsdistCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize dnsdist stats."""
        await self._async_ensure_history_loaded()

        url = f"{self._base_url}/api/v1/servers/localhost/statistics"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}

        session = async_get_clientsession(self.hass)

        try:
            async with timeout(10):
                async with session.get(url, headers=headers, ssl=self._verify_ssl) as resp:
                    if resp.status != 200:
                        raise ConnectionError(f"HTTP {resp.status}")
                    stats = await resp.json()
        except Exception as err:
            _LOGGER.warning("[%s] Fetch error: %s", self._name, err)
            # Preserve last data to avoid sensor going unavailable
            data = dict(self.data or self._zero_data())
            return data

        _LOGGER.debug("[%s] Raw dnsdist stats (first 10): %s", self._name, stats[:10] if isinstance(stats, list) else stats)

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
                        normalized["cpu"] = round(max(0.0, min(cpu_percent, 100.0)), 2)
                self._last_cpu_user_msec = int(cpu_user_msec)
                self._last_update_ts = now_mono
        except Exception as err:
            _LOGGER.debug("[%s] CPU computation failed: %s", self._name, err)

        # --- Compute rolling-window request rates (rounded to unit) ---
        try:
            now_ts = time.time()
            q = int(normalized.get("queries", 0))
            history_changed = False
            # Reset history if counter went backwards (service restart)
            if self._history and q < self._history[-1][1]:
                self._history.clear()
            self._history.append((now_ts, q))
            history_changed = True
            # Trim to last 24h
            cutoff_24h = now_ts - 86400
            while self._history and self._history[0][0] < cutoff_24h:
                self._history.popleft()
                history_changed = True

            if history_changed:
                self._history_dirty = True

            # Helper to compute total requests over the trailing window without
            # normalizing the value to a full period. This ensures the reported
            # rate reflects the actual volume observed in the rolling window
            # instead of an extrapolated value.
            def window_total(window_seconds: int, current_total: int) -> int:
                """Return observed requests inside the trailing window."""

                if not self._history:
                    return 0

                horizon = now_ts - window_seconds
                prev_ts, prev_q = self._history[0]
                baseline = float(prev_q)

                if prev_ts < horizon:
                    for ts, qq in islice(self._history, 1, None):
                        if ts < horizon:
                            prev_ts, prev_q = ts, qq
                            continue

                        if ts == horizon:
                            baseline = float(qq)
                        else:
                            span = ts - prev_ts
                            if span > 0:
                                fraction = (horizon - prev_ts) / span
                                fraction = max(0.0, min(1.0, fraction))
                                baseline = float(prev_q) + (qq - prev_q) * fraction
                            else:
                                baseline = float(prev_q)
                        break
                    else:
                        baseline = float(self._history[-1][1])
                else:
                    baseline = float(prev_q)

                delta = current_total - int(baseline)
                return max(0, delta)

            reqph = window_total(3600, q)      # requests observed in the last hour
            reqpd = window_total(86400, q)     # requests observed in the last 24 hours

            normalized[ATTR_REQ_PER_HOUR] = reqph
            normalized[ATTR_REQ_PER_DAY] = reqpd

            # Keep small debug attributes if useful
            # normalized["rate_windows"] = {"hour_elapsed_s": int(elapsed1), "day_elapsed_s": int(elapsed2)}
        except Exception as err:
            _LOGGER.debug("[%s] Rate computation failed: %s", self._name, err)

        await self._async_save_history()

        try:
            rules = await self._async_fetch_filtering_rules(session, headers)
            if rules is not None:
                normalized[ATTR_FILTERING_RULES] = rules
        except Exception as err:
            _LOGGER.debug("[%s] Filtering rules fetch failed: %s", self._name, err)

        return normalized

    async def _async_ensure_history_loaded(self) -> None:
        """Load persisted history once so rate sensors survive restarts."""

        if self._history_loaded:
            return

        self._history_loaded = True

        try:
            stored = await self._history_store.async_load()
        except Exception as err:
            _LOGGER.debug("[%s] Failed to load history: %s", self._name, err)
            return

        if not isinstance(stored, dict):
            return

        entries = stored.get(STORAGE_KEY_HISTORY)
        if not isinstance(entries, list):
            return

        cutoff = time.time() - 86400
        history: list[tuple[float, int]] = []

        for item in entries:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            ts_raw, val_raw = item
            try:
                ts = float(ts_raw)
                queries = int(val_raw)
            except (TypeError, ValueError):
                continue
            if ts < cutoff:
                continue
            history.append((ts, queries))

        if history:
            history.sort(key=lambda x: x[0])
            self._history = deque(history)
        self._history_dirty = False

    async def _async_save_history(self) -> None:
        """Persist the rolling history so restarts keep accurate rates."""

        if not self._history_loaded or not self._history_dirty:
            return

        if self._last_history_persist is not None:
            if monotonic() - self._last_history_persist < 30:
                return

        payload = {
            STORAGE_KEY_HISTORY: [(float(ts), int(val)) for ts, val in self._history],
        }

        try:
            await self._history_store.async_save(payload)
            self._history_dirty = False
            self._last_history_persist = monotonic()
        except Exception as err:
            _LOGGER.debug("[%s] Failed to save history: %s", self._name, err)

    def _zero_data(self) -> dict[str, Any]:
        return {
            "queries": 0,
            "responses": 0,
            "drops": 0,
            "rule_drop": 0,
            "downstream_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cacheHit": 0,
            "cpu": 0.0,
            "cpu_user_msec": 0,
            "uptime": 0,
            "security_status": "unknown",
            # new rates as integers
            "req_per_hour": 0,
            "req_per_day": 0,
            ATTR_FILTERING_RULES: {},
        }

    def _normalize(self, stats: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """Normalize dnsdist JSON stats into HA-friendly keys."""
        normalized: dict[str, Any] = self._zero_data()

        try:
            items = stats if isinstance(stats, list) else stats.get("statistics", [])
            for item in items:
                key = item.get("name")
                val = item.get("value")

                if key == "queries":
                    normalized["queries"] = int(val)
                elif key == "responses":
                    normalized["responses"] = int(val)
                elif key == "drops":
                    normalized["drops"] = int(val)
                elif key in ("rule-drop", "rule_drop"):
                    normalized["rule_drop"] = int(val)
                elif key in ("downstream-send-errors", "downstream_errors"):
                    normalized["downstream_errors"] = int(val)
                elif key in ("cache-hits", "cache_hits"):
                    normalized["cache_hits"] = int(val)
                elif key in ("cache-misses", "cache_misses"):
                    normalized["cache_misses"] = int(val)
                elif key in ("uptime",):
                    normalized["uptime"] = int(val)
                elif key in ("cpu-user-msec", "cpu_user_msec"):
                    normalized["cpu_user_msec"] = int(val)
                elif key in ("security-status", "security_status"):
                    sec = int(val)
                    if sec == 0:
                        normalized["security_status"] = "unknown"
                    elif sec == 1:
                        normalized["security_status"] = "ok"
                    elif sec == 2:
                        normalized["security_status"] = "warning"
                    elif sec == 3:
                        normalized["security_status"] = "critical"

            # Compute cache hit % (rounded to 0 decimals to match % as integer? keep 2 decimals if you prefer)
            hits = normalized["cache_hits"]
            misses = normalized["cache_misses"]
            denom = hits + misses
            if denom > 0:
                normalized["cacheHit"] = round((hits / denom) * 100, 2)
        except Exception as err:
            _LOGGER.warning("[%s] Failed to normalize data: %s", self._name, err)

        return normalized

    async def _async_fetch_filtering_rules(self, session, headers) -> dict[str, dict[str, Any]] | None:
        """Fetch filtering rules and normalize them into a mapping."""

        if self._filtering_rules_supported is False:
            return None

        url = f"{self._base_url}/api/v1/servers/localhost"
        payload: Any | None = None

        try:
            async with timeout(10):
                async with session.get(url, headers=headers, ssl=self._verify_ssl) as resp:
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

        def _coerce_int(value: Any) -> int:
            try:
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str):
                    return int(float(value))
            except (TypeError, ValueError):
                return 0
            return 0

        name = str(item.get("name") or item.get("rule") or item.get("uuid") or item.get("id") or "Unnamed Rule").strip()
        if not name:
            name = "Unnamed Rule"

        matches = 0
        for key in ("matches", "numMatches", "hits", "num_hits", "hitCount", "count"):
            if key in item:
                matches = _coerce_int(item.get(key))
                break

        slug_source = item.get("uuid") or item.get("id") or name
        slug = self._slugify_rule(slug_source)

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

    def _slugify_rule(self, value: Any) -> str:
        base = str(value or "").lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        if not base:
            base = f"rule-{abs(hash(value)) & 0xFFFF:x}"
        return base
