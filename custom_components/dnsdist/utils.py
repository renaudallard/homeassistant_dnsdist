"""Shared utilities for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from collections.abc import Sequence
from itertools import islice
from time import monotonic
from typing import Any, Deque, Tuple

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, STORAGE_KEY_HISTORY

_LOGGER = logging.getLogger(__name__)

# Pre-compiled pattern for slugifying strings
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: Any, fallback: str = "unknown") -> str:
    """Convert a value to a URL-safe slug.

    Args:
        value: The value to slugify.
        fallback: Default slug if value produces empty result.

    Returns:
        A lowercase alphanumeric slug with hyphens.
    """
    base = str(value or "").lower()
    base = SLUG_PATTERN.sub("-", base).strip("-")
    if not base:
        base = fallback
    return base


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


def build_device_info(coordinator: DataUpdateCoordinator[Any], is_group: bool) -> DeviceInfo:
    """Build device information shared by entities.

    Args:
        coordinator: The data coordinator instance (DnsdistCoordinator or DnsdistGroupCoordinator).
        is_group: Whether this is a group coordinator.

    Returns:
        DeviceInfo dictionary for Home Assistant.
    """
    name = getattr(coordinator, "_name", "dnsdist")
    identifier = f"group:{name}" if is_group else f"host:{name}"

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
