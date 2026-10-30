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
from datetime import timedelta
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_CPU,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_DYNAMIC_RULES,
    ATTR_FILTERING_RULES,
    ATTR_MEMBERS,
    ATTR_QUERIES,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    CONF_NAME,
    DOMAIN,
    HISTORY_SAVE_INTERVAL,
    HOLD_POLLS_FOR_MISSING_MEMBER,
    SIGNAL_DNSDIST_RELOAD,
    STORAGE_KEY_GROUP,
    STORAGE_VERSION,
)
from .utils import coerce_int, is_group_entry, slugify_rule

_LOGGER = logging.getLogger(__name__)

# The members' TOTAL_INCREASING counters, which the group keeps its own total of
COUNTER_KEYS = (
    ATTR_QUERIES,
    ATTR_RESPONSES,
    ATTR_DROPS,
    ATTR_RULE_DROP,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_CACHE_HITS,
    ATTR_CACHE_MISSES,
)


def _served(last: int | None, now: int) -> int:
    """Return what a counter grew by since it was last read.

    A counter that went backwards belongs to a dnsdist that restarted, and
    everything it reports now has been served since it came back.
    """
    if last is None:
        return 0
    return now - last if now >= last else now


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
        # Empty until the first aggregate the group has actually worked out.
        # Publishing zeros instead would make the counters read zero whenever
        # the group loads before its members, and a TOTAL_INCREASING sensor
        # dropping to zero restarts the long term statistics. With the key
        # simply absent the sensor reads unknown, which the statistics skip.
        self._last_data: dict[str, Any] = {}
        # Consecutive polls spent holding the last reading
        self._held_polls = 0
        # The group's own counters, None until the first aggregate. Summing the
        # members' counters instead makes the total fall whenever one of them
        # restarts, is missing or leaves, and a falling TOTAL_INCREASING sensor
        # is a meter reset that adds the whole value to the statistics again.
        # So the group counts what each member served since it was last read,
        # and keeps that next to the readings it was worked out from.
        self._totals: dict[str, int] | None = None
        self._rule_totals: dict[str, int] = {}
        self._seen: dict[str, dict[str, Any]] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_{STORAGE_KEY_GROUP}",
        )
        self._store_loaded = False
        self._unsub_dispatcher = async_dispatcher_connect(hass, SIGNAL_DNSDIST_RELOAD, self._handle_reload_signal)
        _LOGGER.info("Initialized dnsdist group '%s' with members: %s", name, ", ".join(self._members))

    @callback
    def _handle_reload_signal(self) -> None:
        """React to host addition/removal and trigger immediate refresh."""
        if self.hass.data.get(DOMAIN, {}).get(self._entry_id) is not self:
            # Our own entry is on its way out. Unload drops us from hass.data
            # before it sends the signal, while the listener only goes once the
            # unload callbacks run, so the signal still reaches us here.
            _LOGGER.debug("[%s] Ignoring reload signal, the entry is unloading", self._name)
            return

        _LOGGER.debug("[%s] Received reload signal, forcing refresh", self._name)
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Aggregate metrics from active member coordinators."""
        await self._async_ensure_store_loaded()

        try:
            all_coords = self.hass.data.get(DOMAIN, {})
            member_states = self._member_states(all_coords)
            active_members = []

            for _, c in all_coords.items():
                if not hasattr(c, "_name"):
                    continue
                # A member with no reading yet, still on its first poll or down
                # since it loaded, has no counters to add up.
                if c._name in self._members and c.last_update_success and c.data and ATTR_QUERIES in c.data:
                    active_members.append(c)

            if not active_members:
                if self._should_hold("no members are loaded"):
                    return {**self._last_data, ATTR_MEMBERS: member_states}
                return {ATTR_MEMBERS: member_states}

            # The first total is the members' counters summed, which is what
            # the group published before it kept one of its own. Taken with a
            # member missing it would start below that and read as a reset, so
            # wait for every member the user still has configured, but not for
            # ever: one whose setup fails never reports at all.
            expected = set(self._expected_members())
            if self._totals is None:
                active_names = {c._name for c in active_members}
                waiting = sorted(expected - active_names)
                if waiting and self._should_hold(f"waiting for {', '.join(waiting)}"):
                    return {**self._last_data, ATTR_MEMBERS: member_states}
            self._held_polls = 0

            readings: dict[str, tuple[Any, dict[str, int], dict[str, int] | None]] = {}
            # Each member works out its own rates over its own history, so the
            # group has none of its own to keep. Summing what they report
            # survives a member restarting, leaving or coming back, none of
            # which a counter summed across the group can tell from traffic.
            rates = {
                ATTR_REQ_PER_HOUR: 0,
                ATTR_REQ_PER_DAY: 0,
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
                counters = {k: coerce_int(d.get(k)) for k in COUNTER_KEYS}
                member_rules: dict[str, int] | None = None

                # A host that cannot be reached goes on publishing its last
                # figures. Its counters can stay, they describe traffic that
                # really happened, but its rates describe traffic it is no
                # longer serving, so they have to lapse.
                if getattr(c, "reachable", None) is not False:
                    for k in rates:
                        rates[k] += int(d.get(k, 0) or 0)

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
                    member_rules = {}
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
                        member_rules[agg_slug] = member_rules.get(agg_slug, 0) + matches

                        for key in ("id", "uuid", "action", "rule", "type", "enabled", "bypass"):
                            if key in rule and key not in entry and rule[key] is not None:
                                entry[key] = rule[key]

                readings[c._name] = (getattr(c, "_history_source", None), counters, member_rules)

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

            totals = self._count(readings)
            for slug, entry in aggregated_rules.items():
                entry["matches"] = self._rule_totals[slug]

            avg_cpu = round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0.0
            max_uptime = max(uptime_values) if uptime_values else 0

            priority = {"critical": 3, "warning": 2, "ok": 1, "secure": 1, "unknown": 0}
            sec_values.sort(key=lambda s: priority.get(s, 0), reverse=True)
            sec_status = sec_values[0] if sec_values else "unknown"

            aggregated = {
                **totals,
                **rates,
                ATTR_CACHE_HITRATE: round(
                    (totals[ATTR_CACHE_HITS] / (totals[ATTR_CACHE_HITS] + totals[ATTR_CACHE_MISSES])) * 100, 2
                )
                if (totals[ATTR_CACHE_HITS] + totals[ATTR_CACHE_MISSES]) > 0
                else 0.0,
                ATTR_CPU: avg_cpu,
                ATTR_UPTIME: max_uptime,
                ATTR_SECURITY_STATUS: sec_status,
                ATTR_MEMBERS: member_states,
            }

            # The rule aggregate keeps its own, stricter gate. Every member has
            # a coordinator loaded by now, but one of them may still have failed
            # its own poll, and a member that is down publishes no rules at all.
            # Holding a counter reading for a member that never comes back only
            # freezes a figure, where letting the rules shrink deletes entities
            # and the history behind them, so this one waits for all of them.
            quorum = len(active_members) >= len(expected)
            rules_complete = quorum and rules_reporters >= self._count_reporters(
                active_members, "_server_config_supported"
            )
            if rules_complete:
                # The rule is gone from every member, so a rule taking its name
                # later on starts a total of its own.
                self._rule_totals = {slug: n for slug, n in self._rule_totals.items() if slug in aggregated_rules}
            self._publish_aggregate(aggregated, ATTR_FILTERING_RULES, aggregated_rules, rules_complete)
            self._publish_aggregate(
                aggregated,
                ATTR_DYNAMIC_RULES,
                aggregated_dynamic,
                quorum and dynamic_reporters >= self._count_reporters(active_members, "_dynamic_rules_supported"),
            )

            self._last_data = aggregated
            self._store.async_delay_save(self._store_payload, HISTORY_SAVE_INTERVAL)
            _LOGGER.debug("[%s] Aggregated stats: %s", self._name, aggregated)
            return aggregated

        except Exception as err:
            _LOGGER.warning("[%s] Aggregation error: %s", self._name, err)
            return self._last_data

    def _count(self, readings: dict[str, tuple[Any, dict[str, int], dict[str, int] | None]]) -> dict[str, int]:
        """Move the group's own counters on by what each member served.

        A member seen for the first time, or pointed at a different dnsdist
        since, adds nothing on that reading: its counter is a lifetime the
        group never watched go past. One that was absent for a while adds the
        traffic it served meanwhile, which really happened. A rule keeps the
        same kind of total, started from the members' matches summed the first
        time the group sees it.
        """
        first = self._totals is None
        if self._totals is None:
            self._totals = {k: sum(counters[k] for _, counters, _ in readings.values()) for k in COUNTER_KEYS}

        new_rules: dict[str, int] = {}
        for _, _, rules in readings.values():
            for slug, matches in (rules or {}).items():
                if slug not in self._rule_totals:
                    new_rules[slug] = new_rules.get(slug, 0) + matches

        for name, (source, counters, rules) in readings.items():
            prev = self._seen.get(name)
            known = prev is not None and prev.get("source") == source
            last_counters = prev["counters"] if known and prev is not None else {}
            last_rules = prev["rules"] if known and prev is not None else {}

            if not first:
                for k in COUNTER_KEYS:
                    self._totals[k] += _served(last_counters.get(k), counters[k])

            if rules is not None:
                for slug, matches in rules.items():
                    if slug in self._rule_totals:
                        self._rule_totals[slug] += _served(last_rules.get(slug), matches)

            self._seen[name] = {
                "source": source,
                "counters": counters,
                "rules": rules if rules is not None else last_rules,
            }

        self._rule_totals.update(new_rules)
        for name in [n for n in self._seen if n not in self._members]:
            del self._seen[name]

        return dict(self._totals)

    async def _async_ensure_store_loaded(self) -> None:
        """Pick up the totals from before a restart or a reload, once."""
        if self._store_loaded:
            return

        self._store_loaded = True
        try:
            stored = await self._store.async_load()
        except Exception as err:
            _LOGGER.debug("[%s] Failed to load the group totals: %s", self._name, err)
            return

        self._restore(stored)

    def _restore(self, stored: Any) -> None:
        """Take the stored totals, or nothing at all if any part is unreadable."""
        if not isinstance(stored, dict):
            return

        totals = stored.get("totals")
        rule_totals = stored.get("rules")
        seen = stored.get("members")
        if not isinstance(totals, dict) or not isinstance(rule_totals, dict) or not isinstance(seen, dict):
            return
        if not all(isinstance(totals.get(k), int) for k in COUNTER_KEYS):
            return

        members: dict[str, dict[str, Any]] = {}
        for name, item in seen.items():
            if not isinstance(item, dict):
                continue
            counters = item.get("counters")
            rules = item.get("rules")
            if not isinstance(counters, dict) or not isinstance(rules, dict):
                continue
            members[name] = {
                "source": item.get("source"),
                "counters": {k: v for k, v in counters.items() if isinstance(v, int)},
                "rules": {k: v for k, v in rules.items() if isinstance(v, int)},
            }

        self._totals = {k: totals[k] for k in COUNTER_KEYS}
        self._rule_totals = {k: v for k, v in rule_totals.items() if isinstance(v, int)}
        self._seen = members

    async def async_save_totals(self) -> None:
        """Write the totals now, for the coordinator taking over after a reload.

        The regular save waits a few minutes, and one that has not happened
        yet would leave a reloaded group with no totals to carry on from.
        """
        if self._totals is not None:
            await self._store.async_save(self._store_payload())

    def _store_payload(self) -> dict[str, Any]:
        """Build what the store writes, when it writes it, so it is all one moment."""
        return {
            "totals": self._totals,
            "rules": self._rule_totals,
            "members": self._seen,
        }

    def _should_hold(self, reason: str) -> bool:
        """Say whether to carry the last aggregate forward one more poll.

        Holding is bounded because the assumption behind it, that a member is
        only ever briefly absent, is not something the group can enforce. A
        member entry that fails to set up never reaches hass.data at all, and
        without a floor the group would sit on its last reading for ever while
        the figures went on looking live.
        """
        self._held_polls += 1
        if self._held_polls <= HOLD_POLLS_FOR_MISSING_MEMBER:
            _LOGGER.debug("[%s] Holding the last reading, %s", self._name, reason)
            return True

        if self._held_polls == HOLD_POLLS_FOR_MISSING_MEMBER + 1:
            _LOGGER.warning(
                "[%s] Reporting on the members that are left after %d polls, %s",
                self._name,
                self._held_polls,
                reason,
            )

        return False

    def _member_states(self, all_coords: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Report on each configured member, keyed by slug.

        A member with no coordinator has an entry that is unloaded, disabled or
        gone, which is not the same as a host that will not answer, so it
        reports nothing rather than a failure.
        """
        hosts = {coord._name: coord for coord in all_coords.values() if hasattr(coord, "_host")}

        states: dict[str, dict[str, Any]] = {}
        for member in self._members:
            coord = hosts.get(member)
            states[slugify_rule(member)] = {
                "name": member,
                "reachable": coord.reachable if coord is not None else None,
                "loaded": coord is not None,
            }

        return states

    def _expected_members(self) -> list[str]:
        """Return the members that still have a host entry in Home Assistant.

        A member that is configured but has not finished loading must hold the
        aggregate back, while one whose entry was deleted or disabled must not
        hold it back for ever: a disabled entry is never going to report.
        """
        configured = {
            entry.data.get(CONF_NAME, entry.title)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if not is_group_entry(entry) and not entry.disabled_by
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
