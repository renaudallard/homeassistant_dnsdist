# 202510231345
"""Group coordinator for aggregated PowerDNS dnsdist statistics."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Tuple

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_DNSDIST_RELOAD, ATTR_REQ_PER_HOUR, ATTR_REQ_PER_DAY

_LOGGER = logging.getLogger(__name__)


class DnsdistGroupCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Aggregate multiple dnsdist server coordinators into one logical group."""

    def __init__(self, hass: HomeAssistant, name: str, members: list[str], update_interval: int) -> None:
        """Initialize the group coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"dnsdist_group_{name}",
            update_interval=timedelta(seconds=update_interval),
        )
        self._name = name
        self._members = members or []
        self._last_data: dict[str, Any] = self._zero_data()
        self._history: Deque[Tuple[float, int]] = deque()  # (ts, aggregated_queries)
        async_dispatcher_connect(hass, SIGNAL_DNSDIST_RELOAD, self._handle_reload_signal)
        _LOGGER.info("Initialized dnsdist group '%s' with members: %s", name, ", ".join(self._members))

    @callback
    def _handle_reload_signal(self) -> None:
        """React to host addition/removal and trigger immediate refresh."""
        _LOGGER.debug("[%s] Received reload signal — forcing refresh", self._name)
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Aggregate metrics from active member coordinators."""
        try:
            all_coords = self.hass.data.get(DOMAIN, {})
            if not all_coords:
                return self._last_data

            active_members = []

            for _, c in all_coords.items():
                if not hasattr(c, "_name"):
                    continue
                if c._name in self._members and c.last_update_success and c.data:
                    active_members.append(c)

            if not active_members:
                _LOGGER.debug("[%s] No active members yet", self._name)
                await asyncio.sleep(2)
                return self._last_data

            totals = {
                "queries": 0,
                "responses": 0,
                "drops": 0,
                "rule_drop": 0,
                "downstream_errors": 0,
                "cache_hits": 0,
                "cache_misses": 0,
            }
            cpu_values: list[float] = []
            uptime_values: list[int] = []
            sec_values: list[str] = []

            for c in active_members:
                d = c.data or {}
                for k in totals:
                    totals[k] += int(d.get(k, 0) or 0)

                cpu_val = d.get("cpu")
                try:
                    if cpu_val is not None:
                        cpu_values.append(float(cpu_val))
                except (ValueError, TypeError):
                    _LOGGER.debug("[%s] Skipping invalid CPU value from %s: %s", self._name, c._name, cpu_val)

                uptime = d.get("uptime")
                if isinstance(uptime, (int, float)):
                    uptime_values.append(int(uptime))

                sec = str(d.get("security_status", "unknown")).lower()
                sec_values.append(sec)

            avg_cpu = round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0.0
            max_uptime = max(uptime_values) if uptime_values else 0

            priority = {"critical": 3, "warning": 2, "ok": 1, "secure": 1, "unknown": 0}
            sec_values.sort(key=lambda s: priority.get(s, 0), reverse=True)
            sec_status = sec_values[0] if sec_values else "unknown"

            aggregated = {
                **totals,
                "cacheHit": round(
                    (totals["cache_hits"] / (totals["cache_hits"] + totals["cache_misses"])) * 100, 2
                )
                if (totals["cache_hits"] + totals["cache_misses"]) > 0
                else 0.0,
                "cpu": avg_cpu,
                "uptime": max_uptime,
                "security_status": sec_status,
            }

            # --- Rolling-window request rates for the group (rounded to unit) ---
            try:
                now_ts = time.time()
                q_total = int(aggregated["queries"])
                if self._history and q_total < self._history[-1][1]:
                    self._history.clear()
                self._history.append((now_ts, q_total))
                cutoff_24h = now_ts - 86400
                while self._history and self._history[0][0] < cutoff_24h:
                    self._history.popleft()

                def rate_over(window_seconds: int) -> float:
                    horizon = now_ts - window_seconds
                    base_ts, base_q = self._history[0]
                    for (ts, qq) in self._history:
                        if ts >= horizon:
                            base_ts, base_q = ts, qq
                            break
                    elapsed = max(1.0, now_ts - base_ts)
                    delta = max(0, q_total - base_q)
                    return (delta * (window_seconds / elapsed)) if elapsed > 0 else 0.0

                reqph = rate_over(3600)
                reqpd_ph = rate_over(86400)

                aggregated[ATTR_REQ_PER_HOUR] = int(round(reqph))
                aggregated[ATTR_REQ_PER_DAY] = int(round(reqpd_ph * 24.0))
            except Exception as err:
                _LOGGER.debug("[%s] Group rate computation failed: %s", self._name, err)

            self._last_data = aggregated
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    def _zero_data(self) -> dict[str, Any]:
        """Provide a valid zeroed dataset so sensors stay available."""
        return {
            "queries": 0,
            "responses": 0,
            "drops": 0,
            "rule_drop": 0,
            "downstream_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cacheHit": 0.0,
            "cpu": 0.0,
            "uptime": 0,
            "security_status": "unknown",
            "req_per_hour": 0,
            "req_per_day": 0,
        }
