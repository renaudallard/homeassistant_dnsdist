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
    CONF_IS_GROUP,
    CONF_NAME,
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
        # Capped at 24 hours worth of samples to bound memory usage.
        self._history: Deque[Tuple[float, int]] = deque(maxlen=(86400 // update_interval) + 1)
        self._history_store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_{STORAGE_KEY_HISTORY}",
        )
        self._history_loaded = False
        self._history_dirty = False
        self._last_history_persist: float | None = None
        self._unsub_dispatcher = async_dispatcher_connect(hass, SIGNAL_DNSDIST_RELOAD, self._handle_reload_signal)
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
            # How many members actually reported, so an empty aggregate can be
            # told apart from members that could not be read.
            rules_reporters = 0
            dynamic_reporters = 0

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
                    rules_reporters += 1
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
                    dynamic_reporters += 1
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

            # The aggregate may only shrink once every member is present and
            # has reported.  A member that is down publishes no rules at all,
            # and taking that as an empty reading would delete the sensors its
            # rules feed.
            quorum = len(active_members) >= len(self._expected_members())
            self._publish_aggregate(
                aggregated,
                ATTR_FILTERING_RULES,
                aggregated_rules,
                quorum and rules_reporters >= self._count_reporters(active_members, "_server_config_supported"),
            )
            self._publish_aggregate(
                aggregated,
                ATTR_DYNAMIC_RULES,
                aggregated_dynamic,
                quorum and dynamic_reporters >= self._count_reporters(active_members, "_dynamic_rules_supported"),
            )

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

            self._async_save_history()

            self._last_data = aggregated
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    def _expected_members(self) -> list[str]:
        """Return the members that still have a host entry in Home Assistant.

        A member that is configured but has not finished loading must hold the
        aggregate back, while one whose entry was deleted or disabled must not
        hold it back for ever: a disabled entry is never going to report.
        """
        configured = {
            entry.data.get(CONF_NAME, entry.title)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if not entry.data.get(CONF_IS_GROUP) and not entry.disabled_by
        }
        return [member for member in self._members if member in configured]

    @staticmethod
    def _count_reporters(active_members: list[Any], support_flag: str) -> int:
        """Count the members that are expected to report on an endpoint.

        A member whose dnsdist answered 404 will never report and must not hold
        the aggregate back for ever, unlike one that is merely unread.
        """
        return sum(1 for member in active_members if getattr(member, support_flag, None) is not False)

    def _publish_aggregate(
        self,
        aggregated: dict[str, Any],
        key: str,
        value: dict[str, Any],
        complete: bool,
    ) -> None:
        """Store an aggregated mapping, letting it shrink only when complete.

        With every member read the aggregate is the truth, empty included, so
        expired dynblocks and deleted rules lose their sensors.  Short of that
        the last known mapping is kept, and with no last known mapping the key
        is left out entirely: a partial first read is no evidence at all.
        """
        previous = self._last_data.get(key)
        if complete:
            aggregated[key] = value
        elif isinstance(previous, dict):
            aggregated[key] = previous

    def _zero_data(self) -> dict[str, Any]:
        """Provide a valid zeroed dataset so sensors stay available."""
        return make_zero_data()
