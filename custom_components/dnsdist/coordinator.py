"""Coordinator for PowerDNS dnsdist hosts."""

from __future__ import annotations
import logging
from datetime import timedelta
import aiohttp
import async_timeout
from time import monotonic
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_API_KEY,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class DnsdistCoordinator(DataUpdateCoordinator):
    """Fetch and normalize statistics from a dnsdist host."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        port: int,
        api_key: str,
        use_https: bool,
        verify_ssl: bool,
        update_interval: int,
    ):
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
        self._last_cpu_user_msec = None
        self._last_update_ts = None

    async def _async_update_data(self) -> dict:
        """Fetch and normalize dnsdist stats."""
        url = f"{self._base_url}/api/v1/servers/localhost/statistics"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(10):
                    async with session.get(url, headers=headers, ssl=self._verify_ssl) as resp:
                        if resp.status != 200:
                            raise ConnectionError(f"HTTP {resp.status}")
                        stats = await resp.json()
                        _LOGGER.debug("[%s] Raw dnsdist stats (first 10): %s", self._name, stats[:10])
                        normalized = self._normalize(stats)

                        # --- Compute CPU % based on cpu-user-msec counter ---
                        try:
                            cpu_user_msec = normalized.get("cpu_user_msec")
                            now = monotonic()

                            if cpu_user_msec is not None:
                                if self._last_cpu_user_msec is not None and self._last_update_ts is not None:
                                    delta_cpu = cpu_user_msec - self._last_cpu_user_msec
                                    delta_time = now - self._last_update_ts
                                    if delta_time > 0 and delta_cpu >= 0:
                                        cpu_percent = round(((delta_cpu / 1000.0) / delta_time) * 100, 2)
                                        normalized["cpu"] = cpu_percent
                                    else:
                                        normalized["cpu"] = 0.0
                                else:
                                    normalized["cpu"] = 0.0  # first run

                                self._last_cpu_user_msec = cpu_user_msec
                                self._last_update_ts = now
                            else:
                                normalized["cpu"] = 0.0

                            _LOGGER.debug(
                                "[%s] CPU calculation: user_msec=%s last=%s → %.2f%%",
                                self._name,
                                normalized.get("cpu_user_msec"),
                                self._last_cpu_user_msec,
                                normalized.get("cpu"),
                            )
                        except Exception as err:
                            _LOGGER.warning("[%s] CPU calculation failed: %s", self._name, err)
                            normalized["cpu"] = 0.0

                        _LOGGER.debug("[%s] Normalized dnsdist stats: %s", self._name, normalized)
                        return normalized

        except Exception as err:
            _LOGGER.warning("[%s] Failed to fetch data: %s", self._name, err)
            raise

    def _normalize(self, stats: list[dict]) -> dict:
        """Normalize dnsdist JSON stats into HA-friendly keys."""
        normalized = {
            "queries": 0,
            "responses": 0,
            "drops": 0,
            "rule_drop": 0,
            "downstream_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cacheHit": 0.0,
            "cpu": 0.0,
            "cpu_user_msec": None,
            "uptime": 0,
            "security_status": "unknown",
        }

        try:
            for item in stats:
                key = item.get("name")
                val = item.get("value")

                if key == "queries":
                    normalized["queries"] = int(val)
                elif key == "responses":
                    normalized["responses"] = int(val)
                elif key == "drops":
                    normalized["drops"] = int(val)
                elif key == "rule-drop":
                    normalized["rule_drop"] = int(val)
                elif key == "downstream-send-errors":
                    normalized["downstream_errors"] = int(val)
                elif key == "cache-hits":
                    normalized["cache_hits"] = int(val)
                elif key == "cache-misses":
                    normalized["cache_misses"] = int(val)
                elif key == "cpu-user-msec":
                    normalized["cpu_user_msec"] = int(val)
                elif key == "uptime":
                    normalized["uptime"] = int(val)
                elif key == "security-status":
                    sec = int(val)
                    if sec == 0:
                        normalized["security_status"] = "unknown"
                    elif sec == 1:
                        normalized["security_status"] = "ok"
                    elif sec == 2:
                        normalized["security_status"] = "warning"
                    elif sec == 3:
                        normalized["security_status"] = "critical"

            # Compute cache hit %
            hits = normalized["cache_hits"]
            misses = normalized["cache_misses"]
            denom = hits + misses
            if denom > 0:
                normalized["cacheHit"] = round((hits / denom) * 100, 2)

        except Exception as err:
            _LOGGER.warning("[%s] Failed to normalize data: %s", self._name, err)

        return normalized
