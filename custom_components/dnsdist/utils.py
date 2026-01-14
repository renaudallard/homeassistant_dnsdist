"""Shared utilities for PowerDNS dnsdist integration."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

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


def build_device_info(coordinator, is_group: bool) -> DeviceInfo:
    """Build device information shared by entities.

    Args:
        coordinator: The data coordinator instance.
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
