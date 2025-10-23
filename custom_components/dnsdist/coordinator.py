# 202510231345
"""Coordinator for PowerDNS dnsdist hosts."""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta
from asyncio import timeout
from time import monotonic
from typing import Any, Deque, Tuple

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_HOST,
    CONF_PORT,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
)

_LOGGER = logging.getLogger(__name__)


class DnsdistCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls a single dnsdist host."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize dnsdist stats."""
        url = f"{self._base_url}/api/v1/servers/localhost/statistics"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}

        try:
            async with aiohttp.ClientSession() as session:
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
            # Reset history if counter went backwards (service restart)
            if self._history and q < self._history[-1][1]:
                self._history.clear()
            self._history.append((now_ts, q))
            # Trim to last 24h
            cutoff_24h = now_ts - 86400
            while self._history and self._history[0][0] < cutoff_24h:
                self._history.popleft()

            # Helper to compute normalized rate over window_seconds
            def rate_over(window_seconds: int) -> float:
                horizon = now_ts - window_seconds
                base_ts, base_q = self._history[0]
                for (ts, qq) in self._history:
                    if ts >= horizon:
                        base_ts, base_q = ts, qq
                        break
                elapsed = max(1.0, now_ts - base_ts)
                delta = max(0, q - base_q)
                return (delta * (window_seconds / elapsed)) if elapsed > 0 else 0.0

            reqph = rate_over(3600)      # requests per hour over last hour window (normalized)
            reqpd_ph = rate_over(86400)  # per-hour over 24h window

            # Round to whole units
            normalized[ATTR_REQ_PER_HOUR] = int(round(reqph))
            normalized[ATTR_REQ_PER_DAY] = int(round(reqpd_ph * 24.0))

            # Keep small debug attributes if useful
            # normalized["rate_windows"] = {"hour_elapsed_s": int(elapsed1), "day_elapsed_s": int(elapsed2)}
        except Exception as err:
            _LOGGER.debug("[%s] Rate computation failed: %s", self._name, err)

        return normalized

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
