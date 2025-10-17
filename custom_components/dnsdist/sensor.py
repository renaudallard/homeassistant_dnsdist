"""Sensors for PowerDNS dnsdist integration."""

from __future__ import annotations
import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up dnsdist sensors for a host or group."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = coordinator._name
    sensors = []

    metric_map = {
        "queries": ("Total Queries", None, "mdi:dns"),
        "responses": ("Responses", None, "mdi:send"),
        "drops": ("Dropped Queries", None, "mdi:cancel"),
        "rule_drop": ("Rule Drops", None, "mdi:shield-off-outline"),
        "downstream_errors": ("Downstream Send Errors", None, "mdi:arrow-down-thick"),
        "cache_hits": ("Cache Hits", None, "mdi:database-check"),
        "cache_misses": ("Cache Misses", None, "mdi:database-remove"),
        "cacheHit": ("Cache Hit Rate", PERCENTAGE, "mdi:gauge"),
        "cpu": ("CPU Usage", PERCENTAGE, "mdi:cpu-64-bit"),
        "uptime": ("Uptime", UnitOfTime.SECONDS, "mdi:timer-outline"),
        "security_status": ("Security Status", None, "mdi:shield-check-outline"),
    }

    for key, (label, unit, icon) in metric_map.items():
        sensors.append(DnsdistSensor(coordinator, key, f"{name} {label}", unit, icon))

    async_add_entities(sensors)


class DnsdistSensor(CoordinatorEntity, SensorEntity):
    """Representation of a dnsdist metric sensor (host or group)."""

    def __init__(self, coordinator, key, label, unit, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = label
        self._attr_unique_id = f"{coordinator._name}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_should_poll = False

    @property
    def native_value(self):
        """Return the current value."""
        val = self.coordinator.data.get(self._key) if self.coordinator.data else None

        # Keep uptime numeric
        if self._key == "uptime" and isinstance(val, (int, float)):
            return int(val)

        # Percentages
        if self._key in ("cacheHit", "cpu") and isinstance(val, (int, float)):
            return round(val, 2)

        # Security status as lowercase string
        if self._key == "security_status" and isinstance(val, str):
            return val.lower()

        return val

    @property
    def icon(self):
        """Return a dynamic icon for security status."""
        if self._key == "security_status":
            status = str(self.native_value).lower() if self.native_value else "unknown"
            return {
                "ok": "mdi:shield-check",
                "secure": "mdi:shield-check",
                "warning": "mdi:shield-alert",
                "critical": "mdi:shield-alert-outline",
                "unknown": "mdi:shield-off",
            }.get(status, "mdi:shield-off")
        return self._attr_icon

    @property
    def extra_state_attributes(self):
        """Return additional attributes for clarity."""
        attrs = {}
        val = self.coordinator.data.get(self._key) if self.coordinator.data else None

        # Human-readable uptime
        if self._key == "uptime" and isinstance(val, (int, float)):
            days = int(val // 86400)
            hours = int((val % 86400) // 3600)
            minutes = int((val % 3600) // 60)
            attrs["human_readable"] = f"{days}d {hours:02d}h {minutes:02d}m"

        # Security-status details
        elif self._key == "security_status":
            status = str(self.native_value).lower()
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
    def device_info(self):
        """Return device info for this dnsdist hub or group."""
        # Detect whether this coordinator represents a group or a host
        is_group = hasattr(self.coordinator, "_members") or "group" in self.coordinator.name.lower()

        info = {
            "identifiers": {(DOMAIN, self.coordinator._name)},
            "name": self.coordinator._name,
            "manufacturer": "PowerDNS",
            "model": "dnsdist Group" if is_group else "dnsdist Host",
            "entry_type": "service",
        }

        # Only include a URL for real hosts (groups have no direct API)
        if not is_group and hasattr(self.coordinator, "_host"):
            proto = "https" if getattr(self.coordinator, "_use_https", False) else "http"
            info["configuration_url"] = f"{proto}://{self.coordinator._host}:{self.coordinator._port}"

        return info
