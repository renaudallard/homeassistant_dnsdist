"""Group coordinator for aggregated PowerDNS dnsdist statistics."""

from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_DNSDIST_RELOAD

_LOGGER = logging.getLogger(__name__)


class DnsdistGroupCoordinator(DataUpdateCoordinator):
    """Aggregate multiple dnsdist server coordinators into one logical group."""

    def __init__(self, hass: HomeAssistant, name: str, members: list[str], update_interval: int):
        """Initialize the group coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"dnsdist_group_{name}",
            update_interval=timedelta(seconds=update_interval),
        )
        self._name = name
        self._members = members or []
        self._last_data: dict = self._zero_data()
        async_dispatcher_connect(hass, SIGNAL_DNSDIST_RELOAD, self._handle_reload_signal)
        _LOGGER.info("Initialized dnsdist group '%s' with members: %s", name, ", ".join(self._members))

    @callback
    def _handle_reload_signal(self):
        """React to host addition/removal and trigger immediate refresh."""
        _LOGGER.debug("[%s] Received reload signal — forcing refresh", self._name)
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict:
        """Aggregate metrics from active member coordinators."""
        try:
            all_coords = self.hass.data.get(DOMAIN, {})
            if not all_coords:
                return self._last_data

            active_members = []
            for m in self._members:
                c = next((c for c in all_coords.values() if getattr(c, "_name", None) == m), None)
                if c and c.last_update_success and c.data:
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
            cpu_values, uptime_values, sec_values = [], [], []

            for c in active_members:
                d = c.data or {}
                for k in totals:
                    totals[k] += d.get(k, 0) or 0

                cpu_val = d.get("cpu")
                try:
                    if cpu_val is not None:
                        cpu_values.append(float(cpu_val))
                except (ValueError, TypeError):
                    _LOGGER.debug("[%s] Skipping invalid CPU value from %s: %s", self._name, c._name, cpu_val)

                if isinstance(d.get("uptime"), (int, float)):
                    uptime_values.append(d["uptime"])
                if d.get("security_status"):
                    sec_values.append(d["security_status"])

            denom = totals["cache_hits"] + totals["cache_misses"]
            cache_rate = round((totals["cache_hits"] / denom) * 100, 2) if denom > 0 else 0.0
            avg_cpu = round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0.0
            max_uptime = max(uptime_values) if uptime_values else 0
            _LOGGER.debug("[%s] Member CPU values: %s → avg %.2f", self._name, cpu_values, avg_cpu)

            mapping = {"unknown": 0, "ok": 1, "secure": 1, "warning": 2, "critical": 3}
            reverse_map = {0: "unknown", 1: "ok", 2: "warning", 3: "critical"}

            if sec_values:
                max_numeric = max(mapping.get(s, 0) for s in sec_values)
                sec_status = reverse_map[max_numeric]
            else:
                sec_status = "unknown"

            aggregated = {
                **totals,
                "cacheHit": cache_rate,
                "cpu": avg_cpu,
                "uptime": max_uptime,  # ✅ highest uptime wins
                "security_status": sec_status,
            }

            self._last_data = aggregated
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    def _zero_data(self) -> dict:
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
        }
