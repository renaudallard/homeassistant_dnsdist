"""Group coordinator for aggregated PowerDNS dnsdist statistics."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from datetime import timedelta
from itertools import islice
from typing import Any, Deque, Tuple

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_DNSDIST_RELOAD,
    ATTR_REQ_PER_HOUR,
    ATTR_REQ_PER_DAY,
    ATTR_FILTERING_RULES,
    STORAGE_VERSION,
    STORAGE_KEY_HISTORY,
)

_LOGGER = logging.getLogger(__name__)


class DnsdistGroupCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
            aggregated_rules: dict[str, dict[str, Any]] = {}

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

                rules = d.get(ATTR_FILTERING_RULES)
                if isinstance(rules, dict):
                    source_name = getattr(c, "_name", "dnsdist")
                    for rule in rules.values():
                        if not isinstance(rule, dict):
                            continue

                        base_name = str(rule.get("name") or "Unnamed Rule").strip()
                        if not base_name:
                            base_name = "Unnamed Rule"

                        agg_slug = self._slugify_rule_name(base_name)
                        matches = self._coerce_int(rule.get("matches"))

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

            if aggregated_rules:
                aggregated[ATTR_FILTERING_RULES] = aggregated_rules
            elif ATTR_FILTERING_RULES in self._last_data:
                aggregated[ATTR_FILTERING_RULES] = self._last_data.get(ATTR_FILTERING_RULES, {})

            # --- Rolling-window request totals for the group ---
            try:
                now_ts = time.time()
                q_total = int(aggregated["queries"])
                history_changed = False
                if self._history and q_total < self._history[-1][1]:
                    self._history.clear()
                    history_changed = True
                self._history.append((now_ts, q_total))
                history_changed = True
                cutoff_24h = now_ts - 86400
                while self._history and self._history[0][0] < cutoff_24h:
                    self._history.popleft()
                    history_changed = True

                if history_changed:
                    self._history_dirty = True

                def window_total(window_seconds: int, current_total: int) -> int:
                    """Return observed requests for the trailing window."""

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

                aggregated[ATTR_REQ_PER_HOUR] = window_total(3600, q_total)
                aggregated[ATTR_REQ_PER_DAY] = window_total(86400, q_total)
            except Exception as err:
                _LOGGER.debug("[%s] Group rate computation failed: %s", self._name, err)

            await self._async_save_history()

            self._last_data = aggregated
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    async def _async_ensure_history_loaded(self) -> None:
        """Load persisted group history so restart keeps rolling windows."""

        if self._history_loaded:
            return

        self._history_loaded = True

        try:
            stored = await self._history_store.async_load()
        except Exception as err:
            _LOGGER.debug("[%s] Failed to load group history: %s", self._name, err)
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
        """Persist the aggregated history for restart continuity."""

        if not self._history_loaded or not self._history_dirty:
            return

        if self._last_history_persist is not None:
            if time.monotonic() - self._last_history_persist < 30:
                return

        payload = {
            STORAGE_KEY_HISTORY: [(float(ts), int(val)) for ts, val in self._history],
        }

        try:
            await self._history_store.async_save(payload)
            self._history_dirty = False
            self._last_history_persist = time.monotonic()
        except Exception as err:
            _LOGGER.debug("[%s] Failed to save group history: %s", self._name, err)

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
            ATTR_FILTERING_RULES: {},
        }

    def _coerce_int(self, value: Any) -> int:
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

    def _slugify(self, value: Any) -> str:
        base = str(value or "").lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        if not base:
            base = "group"
        return base

    def _slugify_rule_name(self, value: Any) -> str:
        base = str(value or "").lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        if not base:
            base = f"rule-{abs(hash(value)) & 0xFFFF:x}"
        return base
