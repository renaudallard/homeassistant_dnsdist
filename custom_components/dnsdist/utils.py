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

"""Shared utilities for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from collections.abc import Callable, Sequence
from itertools import islice
from time import monotonic
from typing import Any, Deque, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_CPU,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_FILTERING_RULES,
    ATTR_QUERIES,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    DOMAIN,
    DYNAMIC_ENTITY_PREFIXES,
    STORAGE_KEY_HISTORY,
)

_LOGGER = logging.getLogger(__name__)

# Pre-compiled pattern for slugifying strings
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify_rule(value: Any) -> str:
    """Slugify a filtering rule name with hash fallback."""
    base = str(value or "").lower()
    base = SLUG_PATTERN.sub("-", base).strip("-")
    if not base:
        base = f"rule-{abs(hash(value)) & 0xFFFF:x}"
    return base


def coerce_int(value: Any) -> int:
    """Safely convert a value to integer.

    Handles bool, int, float, and string types.
    Returns 0 for unconvertible values.
    """
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


def device_identifier(name: str, is_group: bool) -> str:
    """Build the device registry identifier for a host or group."""
    return f"group:{name}" if is_group else f"host:{name}"


def build_device_info(coordinator: DataUpdateCoordinator[Any], is_group: bool) -> DeviceInfo:
    """Build device information shared by entities.

    Args:
        coordinator: The data coordinator instance (DnsdistCoordinator or DnsdistGroupCoordinator).
        is_group: Whether this is a group coordinator.

    Returns:
        DeviceInfo dictionary for Home Assistant.
    """
    name = getattr(coordinator, "_name", "dnsdist")
    identifier = device_identifier(name, is_group)

    info: DeviceInfo = DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        name=name,
        manufacturer="PowerDNS",
        model="dnsdist Group" if is_group else "dnsdist Host",
        entry_type=None,
    )

    if not is_group and hasattr(coordinator, "_host"):
        proto = "https" if getattr(coordinator, "_use_https", False) else "http"
        info["configuration_url"] = f"{proto}://{coordinator._host}:{coordinator._port}"

    return info


def split_dynamic_unique_id(unique_id: str, entry_id: str) -> tuple[str | None, str]:
    """Split a unique ID into its dynamic entity prefix and slug.

    Returns ``(None, "")`` for the fixed entities (metric sensors, buttons),
    which are never orphaned and must not be touched.
    """
    head = f"{entry_id}:"
    if not unique_id.startswith(head):
        return None, ""

    rest = unique_id[len(head) :]
    for prefix in DYNAMIC_ENTITY_PREFIXES:
        if rest.startswith(prefix):
            return prefix, rest[len(prefix) :]

    return None, ""


def filtering_rule_aliases(data: dict[str, Any]) -> dict[str, str]:
    """Map legacy filtering rule slugs onto the current ones.

    Up to 1.4.2 the slug came from the dnsdist rule UUID, which is regenerated
    every time dnsdist loads its configuration, so the slug now comes from the
    rule name instead.  Mapping the old form to the new one lets a sensor keep
    its entity ID and its history, as long as dnsdist has not reloaded since
    the sensor was created.  Once it has, the old UUID is unknowable and the
    entity is simply removed as the orphan it is.

    The old code also fell back to the rule's position in the chain, but that
    is not aliased here: the position points at whichever rule sits there now,
    which is rarely the one the entity belonged to.
    """
    rules = data.get(ATTR_FILTERING_RULES)
    if not isinstance(rules, dict):
        return {}

    aliases: dict[str, str] = {}
    for slug, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        uuid = rule.get("uuid")
        if not uuid:
            continue
        legacy = slugify_rule(uuid)
        if legacy != slug:
            aliases.setdefault(legacy, slug)

    return aliases


@callback
def async_prune_orphaned_entities(hass: HomeAssistant, entry_id: str, data: Any) -> int:
    """Delete registry entries whose dnsdist object no longer exists.

    Each platform only tracks the entities it created during the current run,
    so a rule, dynblock or backend that disappeared while the entry was
    unloaded would linger forever.  A data key that is absent means the
    endpoint could not be read, not that everything is gone, so that family is
    left alone.

    Returns the number of entities removed.
    """
    if not isinstance(data, dict):
        return 0

    ent_reg = er.async_get(hass)
    aliases = filtering_rule_aliases(data)
    removed = 0

    for entry in er.async_entries_for_config_entry(ent_reg, entry_id):
        prefix, slug = split_dynamic_unique_id(entry.unique_id, entry_id)
        if prefix is None:
            continue

        live = data.get(DYNAMIC_ENTITY_PREFIXES[prefix])
        if not isinstance(live, dict) or slug in live:
            continue

        if prefix == "filtering_rule:" and slug in aliases:
            new_unique_id = f"{entry_id}:{prefix}{aliases[slug]}"
            if not ent_reg.async_get_entity_id(entry.domain, entry.platform, new_unique_id):
                _LOGGER.debug("[dnsdist] Migrating %s to unique ID %s", entry.entity_id, new_unique_id)
                ent_reg.async_update_entity(entry.entity_id, new_unique_id=new_unique_id)
                continue

        _LOGGER.debug("[dnsdist] Removing orphaned entity %s (%s)", entry.entity_id, entry.unique_id)
        ent_reg.async_remove(entry.entity_id)
        removed += 1

    return removed


@callback
def async_prune_orphaned_devices(hass: HomeAssistant, entry_id: str, identifier: str) -> int:
    """Delete devices left behind by a rename.

    The device is keyed on the display name, so renaming a host or group moves
    every entity to a new device and leaves the old one behind empty.  Only
    devices that no longer hold any entity are removed.

    Returns the number of devices removed.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    removed = 0

    for device in dr.async_entries_for_config_entry(dev_reg, entry_id):
        if (DOMAIN, identifier) in device.identifiers:
            continue
        if device.config_entries != {entry_id}:
            # Shared with another entry, which is not ours to delete.
            continue
        if er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True):
            continue

        _LOGGER.debug("[dnsdist] Removing orphaned device %s", device.name)
        dev_reg.async_remove_device(device.id)
        removed += 1

    return removed


@callback
def async_register_slug_platform(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: DataUpdateCoordinator[Any],
    async_add_entities: AddEntitiesCallback,
    *,
    data_key: str,
    factory: Callable[[str], Entity],
) -> None:
    """Keep per-slug entities in step with coordinator data.

    Adds an entity for every slug that shows up and removes the ones whose
    slug disappeared, for as long as the entry stays loaded.
    """
    tracked: dict[str, Entity] = {}

    @callback
    def _async_sync() -> None:
        items = coordinator.data.get(data_key) if isinstance(coordinator.data, dict) else None
        if not isinstance(items, dict):
            # No reading available: leave what we have rather than wiping it.
            return

        stale = set(tracked) - set(items)
        if stale:
            ent_reg = er.async_get(hass)
            for slug in stale:
                entity = tracked.pop(slug)
                _LOGGER.debug("[dnsdist] Removing %s entity for %s", data_key, slug)
                if entity.entity_id and ent_reg.async_get(entity.entity_id):
                    # Drop the registry entry too, or it comes back after a restart.
                    ent_reg.async_remove(entity.entity_id)
                else:
                    hass.async_create_task(entity.async_remove())

        new_entities: list[Entity] = []
        for slug in items:
            if slug in tracked:
                continue
            entity = factory(slug)
            tracked[slug] = entity
            new_entities.append(entity)

        if new_entities:
            _LOGGER.debug("[dnsdist] Adding %s entities: %s", data_key, [e.unique_id for e in new_entities])
            async_add_entities(new_entities)

    _async_sync()
    entry.async_on_unload(coordinator.async_add_listener(_async_sync))


def make_zero_data() -> dict[str, Any]:
    """Create a zeroed data dictionary for coordinators."""
    return {
        ATTR_QUERIES: 0,
        ATTR_RESPONSES: 0,
        ATTR_DROPS: 0,
        ATTR_RULE_DROP: 0,
        ATTR_DOWNSTREAM_ERRORS: 0,
        ATTR_CACHE_HITS: 0,
        ATTR_CACHE_MISSES: 0,
        ATTR_CACHE_HITRATE: 0.0,
        ATTR_CPU: 0.0,
        ATTR_UPTIME: 0,
        ATTR_SECURITY_STATUS: "unknown",
        ATTR_REQ_PER_HOUR: 0,
        ATTR_REQ_PER_DAY: 0,
    }


def compute_window_total(
    history: Sequence[tuple[float, int]],
    now_ts: float,
    window_seconds: int,
    current_total: int,
) -> int:
    """Compute total requests observed in a trailing time window.

    Uses linear interpolation to estimate the baseline value at the
    window boundary when no exact sample exists at that time.

    Args:
        history: Sequence of (timestamp, query_count) tuples, ordered by time.
        now_ts: Current timestamp.
        window_seconds: Size of the trailing window in seconds.
        current_total: Current total query count.

    Returns:
        Number of requests observed within the window (non-negative).
    """
    if not history:
        return 0

    horizon = now_ts - window_seconds
    prev_ts, prev_q = history[0]
    baseline = float(prev_q)

    if prev_ts < horizon:
        for ts, qq in islice(history, 1, None):
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
            # for/else: executes if loop completes without break, meaning all
            # history entries are older than horizon; use the most recent value
            baseline = float(history[-1][1])
    else:
        baseline = float(prev_q)

    delta = current_total - int(baseline)
    return max(0, delta)


class HistoryMixin:
    """Mixin providing history persistence for coordinators.

    Subclasses must define:
        _history: Deque[Tuple[float, int]]
        _history_loaded: bool
        _history_dirty: bool
        _last_history_persist: float | None
        _history_store: Store
        _name: str
    """

    _history: Deque[Tuple[float, int]]
    _history_loaded: bool
    _history_dirty: bool
    _last_history_persist: float | None
    _history_store: Store
    _name: str

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
            self._history = deque(history, maxlen=self._history.maxlen)
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

    def _update_history(self, now_ts: float, query_count: int) -> None:
        """Update history with new data point and trim old entries.

        Resets history if counter went backwards (service restart).
        Trims entries older than 24 hours.
        """
        # Reset history if counter went backwards (service restart)
        if self._history and query_count < self._history[-1][1]:
            self._history.clear()

        self._history.append((now_ts, query_count))
        self._history_dirty = True

        # Trim to last 24h
        cutoff_24h = now_ts - 86400
        while self._history and self._history[0][0] < cutoff_24h:
            self._history.popleft()

    def _compute_rates(self, now_ts: float, query_count: int) -> tuple[int, int]:
        """Compute hourly and daily request rates with extrapolation.

        Returns:
            Tuple of (req_per_hour, req_per_day).
        """
        if not self._history:
            return 0, 0

        oldest_ts = self._history[0][0]
        history_span = now_ts - oldest_ts

        # Hourly rate
        if history_span >= 3600:
            req_per_hour = compute_window_total(self._history, now_ts, 3600, query_count)
        elif history_span > 0:
            observed = query_count - self._history[0][1]
            req_per_hour = int((observed / history_span) * 3600)
        else:
            req_per_hour = 0

        # Daily rate
        if history_span >= 86400:
            req_per_day = compute_window_total(self._history, now_ts, 86400, query_count)
        elif history_span > 0:
            observed = query_count - self._history[0][1]
            req_per_day = int((observed / history_span) * 86400)
        else:
            req_per_day = 0

        return req_per_hour, req_per_day
