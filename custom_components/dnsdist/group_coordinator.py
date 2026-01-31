"""Group coordinator for aggregated PowerDNS dnsdist statistics."""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Tuple

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

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
    SIGNAL_DNSDIST_RELOAD,
    STORAGE_KEY_HISTORY,
    STORAGE_VERSION,
)
from .utils import HistoryMixin, coerce_int, make_zero_data, slugify_rule

_LOGGER = logging.getLogger(__name__)


class DnsdistGroupCoordinator(HistoryMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Aggregate multiple dnsdist server coordinators into one logical group."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        name: str,
        members: list[str],
        update_interval: int,
    ) -> None:
        """Initialize the group coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"dnsdist_group_{name}",
            update_interval=timedelta(seconds=update_interval),
        )
        self._name = name
        self._entry_id = entry_id
        self._members = members or []
        self._last_data: dict[str, Any] = self._zero_data()
        self._history: Deque[Tuple[float, int]] = deque()  # (ts, aggregated_queries)
        self._history_store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_{STORAGE_KEY_HISTORY}",
        )
        self._history_loaded = False
        self._history_dirty = False
        self._last_history_persist: float | None = None
        async_dispatcher_connect(hass, SIGNAL_DNSDIST_RELOAD, self._handle_reload_signal)
        _LOGGER.info("Initialized dnsdist group '%s' with members: %s", name, ", ".join(self._members))

    @callback
    def _handle_reload_signal(self) -> None:
        """React to host addition/removal and trigger immediate refresh."""
        _LOGGER.debug("[%s] Received reload signal — forcing refresh", self._name)
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Aggregate metrics from active member coordinators."""
        await self._async_ensure_history_loaded()
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
                return self._last_data

            totals = {
                ATTR_QUERIES: 0,
                ATTR_RESPONSES: 0,
                ATTR_DROPS: 0,
                ATTR_RULE_DROP: 0,
                ATTR_DOWNSTREAM_ERRORS: 0,
                ATTR_CACHE_HITS: 0,
                ATTR_CACHE_MISSES: 0,
            }
            cpu_values: list[float] = []
            uptime_values: list[int] = []
            sec_values: list[str] = []
            aggregated_rules: dict[str, dict[str, Any]] = {}
            aggregated_dynamic: dict[str, dict[str, Any]] = {}

            for c in active_members:
                d = c.data or {}
                for k in totals:
                    totals[k] += int(d.get(k, 0) or 0)

                cpu_val = d.get(ATTR_CPU)
                try:
                    if cpu_val is not None:
                        cpu_values.append(float(cpu_val))
                except (ValueError, TypeError):
                    _LOGGER.debug("[%s] Skipping invalid CPU value from %s: %s", self._name, c._name, cpu_val)

                uptime = d.get(ATTR_UPTIME)
                if isinstance(uptime, (int, float)):
                    uptime_values.append(int(uptime))

                sec = str(d.get(ATTR_SECURITY_STATUS, "unknown")).lower()
                sec_values.append(sec)

                rules = d.get(ATTR_FILTERING_RULES)
                if isinstance(rules, dict):
                    source_name = getattr(c, "_name", "dnsdist")
                    for rule in rules.values():
                        if not isinstance(rule, dict):
                            continue

                        base_name = str(rule.get("name") or "Unnamed Rule").strip()
                        if not base_name:
                            base_name = "Unnamed Rule"

                        agg_slug = slugify_rule(base_name)
                        matches = coerce_int(rule.get("matches"))

                        entry = aggregated_rules.setdefault(
                            agg_slug,
                            {
                                "name": base_name,
                                "matches": 0,
                                "sources": {},
                            },
                        )

                        entry["matches"] += matches
                        entry_sources = entry.setdefault("sources", {})
                        entry_sources[source_name] = entry_sources.get(source_name, 0) + matches

                        for key in ("id", "uuid", "action", "rule", "type", "enabled", "bypass"):
                            if key in rule and key not in entry and rule[key] is not None:
                                entry[key] = rule[key]

                # Aggregate dynamic rules (dynblocks)
                dynamic_rules = d.get(ATTR_DYNAMIC_RULES)
                if isinstance(dynamic_rules, dict):
                    source_name = getattr(c, "_name", "dnsdist")
                    for rule in dynamic_rules.values():
                        if not isinstance(rule, dict):
                            continue

                        network = str(rule.get("network") or "Unknown").strip()
                        if not network:
                            network = "Unknown"

                        agg_slug = slugify_rule(network)
                        blocks = coerce_int(rule.get("blocks"))

                        entry = aggregated_dynamic.setdefault(
                            agg_slug,
                            {
                                "network": network,
                                "blocks": 0,
                                "sources": {},
                            },
                        )

                        entry["blocks"] += blocks
                        entry_sources = entry.setdefault("sources", {})
                        entry_sources[source_name] = entry_sources.get(source_name, 0) + blocks

                        for key in ("reason", "action", "seconds", "ebpf", "warning"):
                            if key in rule and key not in entry and rule[key] is not None:
                                entry[key] = rule[key]

            avg_cpu = round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0.0
            max_uptime = max(uptime_values) if uptime_values else 0

            priority = {"critical": 3, "warning": 2, "ok": 1, "secure": 1, "unknown": 0}
            sec_values.sort(key=lambda s: priority.get(s, 0), reverse=True)
            sec_status = sec_values[0] if sec_values else "unknown"

            aggregated = {
                **totals,
                ATTR_CACHE_HITRATE: round(
                    (totals[ATTR_CACHE_HITS] / (totals[ATTR_CACHE_HITS] + totals[ATTR_CACHE_MISSES])) * 100, 2
                )
                if (totals[ATTR_CACHE_HITS] + totals[ATTR_CACHE_MISSES]) > 0
                else 0.0,
                ATTR_CPU: avg_cpu,
                ATTR_UPTIME: max_uptime,
                ATTR_SECURITY_STATUS: sec_status,
            }

            if aggregated_rules:
                aggregated[ATTR_FILTERING_RULES] = aggregated_rules
            elif ATTR_FILTERING_RULES in self._last_data:
                aggregated[ATTR_FILTERING_RULES] = self._last_data.get(ATTR_FILTERING_RULES, {})

            if aggregated_dynamic:
                aggregated[ATTR_DYNAMIC_RULES] = aggregated_dynamic
            elif ATTR_DYNAMIC_RULES in self._last_data:
                aggregated[ATTR_DYNAMIC_RULES] = self._last_data.get(ATTR_DYNAMIC_RULES, {})

            # --- Rolling-window request totals for the group ---
            try:
                now_ts = time.time()
                q_total = int(aggregated[ATTR_QUERIES])
                self._update_history(now_ts, q_total)
                req_hour, req_day = self._compute_rates(now_ts, q_total)
                aggregated[ATTR_REQ_PER_HOUR] = req_hour
                aggregated[ATTR_REQ_PER_DAY] = req_day
            except Exception as err:
                _LOGGER.debug("[%s] Group rate computation failed: %s", self._name, err)

            await self._async_save_history()

            self._last_data = aggregated
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    def _zero_data(self) -> dict[str, Any]:
        """Provide a valid zeroed dataset so sensors stay available."""
        return make_zero_data()
