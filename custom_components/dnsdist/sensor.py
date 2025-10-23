# 202510231400
"""Sensors for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_IS_GROUP

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up dnsdist sensors for a host or group."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: list[DnsdistSensor] = []

    # NOTE: Labels below are metric-only. HA will prefix with device (host/group) name
    # because _attr_has_entity_name = True on the entity class.
    metric_map: dict[str, tuple[str, Any, str, SensorStateClass | None]] = {
        "queries": ("Total Queries", None, "mdi:dns", SensorStateClass.TOTAL_INCREASING),
        "responses": ("Responses", None, "mdi:send", SensorStateClass.TOTAL_INCREASING),
        "drops": ("Dropped Queries", None, "mdi:cancel", SensorStateClass.TOTAL_INCREASING),
        "rule_drop": ("Rule Drops", None, "mdi:shield-off-outline", SensorStateClass.TOTAL_INCREASING),
        "downstream_errors": ("Downstream Send Errors", None, "mdi:arrow-down-thick", SensorStateClass.TOTAL_INCREASING),
        "cache_hits": ("Cache Hits", None, "mdi:database-check", SensorStateClass.TOTAL_INCREASING),
        "cache_misses": ("Cache Misses", None, "mdi:database-remove", SensorStateClass.TOTAL_INCREASING),
        "cacheHit": ("Cache Hit Rate", PERCENTAGE, "mdi:gauge", SensorStateClass.MEASUREMENT),
        "cpu": ("CPU Usage", PERCENTAGE, "mdi:cpu-64-bit", SensorStateClass.MEASUREMENT),
        "uptime": ("Uptime", UnitOfTime.SECONDS, "mdi:timer-outline", SensorStateClass.MEASUREMENT),
        # Rate sensors (rounded to whole units by coordinators)
        "req_per_hour": ("Requests per Hour (last hour)", "req/h", "mdi:chart-line", SensorStateClass.MEASUREMENT),
        "req_per_day": ("Requests per Day (last 24h)", "req/d", "mdi:chart-areaspline", SensorStateClass.MEASUREMENT),
        "security_status": ("Security Status", None, "mdi:shield-check-outline", None),
    }

    for key, (label, unit, icon, state_class) in metric_map.items():
        sensors.append(
            DnsdistSensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                key=key,
                label=label,  # IMPORTANT: do NOT prepend device name here
                unit=unit,
                icon=icon,
                state_class=state_class,
                is_group=bool(entry.data.get(CONF_IS_GROUP)),
            )
        )

    async_add_entities(sensors)


class DnsdistSensor(CoordinatorEntity, SensorEntity):
    """Representation of a dnsdist metric sensor (host or group)."""

    # Let HA compose the entity name as "<device name> <entity name>"
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator,
        entry_id: str,
        key: str,
        label: str,
        unit,
        icon: str,
        state_class: SensorStateClass | None,
        is_group: bool,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._is_group = is_group
        self._attr_name = label  # metric-only label
        # Stable unique_id: entry_id + metric key
        self._attr_unique_id = f"{entry_id}:{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_should_poll = False
        self._attr_state_class = state_class

    @property
    def native_value(self):
        """Return the current value."""
        val = None
        try:
            val = self.coordinator.data.get(self._key) if self.coordinator.data else None
        except Exception:
            return None

        if self._key == "uptime" and isinstance(val, (int, float)):
            return int(val)

        # Requests/hour and day are integers already (rounded in coordinators), enforce int
        if self._key in ("req_per_hour", "req_per_day") and isinstance(val, (int, float)):
            return int(val)

        # Percentages rounded to two decimals
        if self._key in ("cacheHit", "cpu") and isinstance(val, (int, float)):
            return round(float(val), 2)

        if self._key == "security_status" and isinstance(val, str):
            return val.lower()

        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Add helpful attributes for uptime and security."""
        attrs: dict[str, Any] = {}

        if self._key == "uptime":
            val = self.native_value
            if isinstance(val, (int, float)):
                days = int(val // 86400)
                hours = int((val % 86400) // 3600)
                minutes = int((val % 3600) // 60)
                attrs["human_readable"] = f"{days}d {hours:02d}h {minutes:02d}m"

        elif self._key == "security_status":
            status = str(self.native_value or "").lower()
            attrs["status_code"] = {
                "unknown": 0,
                "ok": 1,
                "secure": 1,
                "warning": 2,
                "critical": 3,
            }.get(status, 0)
            attrs["status_label"] = {
                "unknown": "Unknown",
                "ok": "OK",
                "secure": "OK",
                "warning": "Upgrade Recommended",
                "critical": "Upgrade Required",
            }.get(status, "Unknown")

        return attrs

    @property
    def device_class(self):
        """Use duration device class for uptime."""
        if self._key == "uptime":
            return SensorDeviceClass.DURATION
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Create a distinct device per host or group."""
        name = getattr(self.coordinator, "_name", "dnsdist")
        is_group = self._is_group
        identifier = f"group:{name}" if is_group else f"host:{name}"

        info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=name,
            manufacturer="PowerDNS",
            model="dnsdist Group" if is_group else "dnsdist Host",
            entry_type=None,
        )

        if not is_group and hasattr(self.coordinator, "_host"):
            proto = "https" if getattr(self.coordinator, "_use_https", False) else "http"
            info["configuration_url"] = f"{proto}://{self.coordinator._host}:{self.coordinator._port}"

        return info
