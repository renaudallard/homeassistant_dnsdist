"""Sensors for PowerDNS dnsdist integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
import homeassistant.const as ha_const
from homeassistant.const import UnitOfTime, PERCENTAGE
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er

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
    CONF_INCLUDE_FILTER_SENSORS,
    CONF_IS_GROUP,
    DOMAIN,
    SECURITY_STATUS_CODE,
    SECURITY_STATUS_LABEL,
)
from .utils import build_device_info

# COUNT constant for sensor units - use HA's COUNT if available, otherwise fallback
COUNT = getattr(ha_const, "COUNT", "count")

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up dnsdist sensors for a host or group."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: list[DnsdistSensor] = []
    is_group = bool(entry.data.get(CONF_IS_GROUP))
    include_filter_sensors = bool(
        entry.data.get(CONF_INCLUDE_FILTER_SENSORS, bool(is_group))
    )

    # NOTE: Labels below are metric-only. HA will prefix with device (host/group) name
    # because _attr_has_entity_name = True on the entity class.
    metric_map: dict[str, tuple[str, Any, str, SensorStateClass | None]] = {
        ATTR_QUERIES: ("Total Queries", COUNT, "mdi:dns", SensorStateClass.TOTAL_INCREASING),
        ATTR_RESPONSES: ("Responses", COUNT, "mdi:send", SensorStateClass.TOTAL_INCREASING),
        ATTR_DROPS: ("Dropped Queries", COUNT, "mdi:cancel", SensorStateClass.TOTAL_INCREASING),
        ATTR_RULE_DROP: ("Rule Drops", COUNT, "mdi:shield-off-outline", SensorStateClass.TOTAL_INCREASING),
        ATTR_DOWNSTREAM_ERRORS: (
            "Downstream Send Errors",
            COUNT,
            "mdi:arrow-down-thick",
            SensorStateClass.TOTAL_INCREASING,
        ),
        ATTR_CACHE_HITS: ("Cache Hits", COUNT, "mdi:database-check", SensorStateClass.TOTAL_INCREASING),
        ATTR_CACHE_MISSES: (
            "Cache Misses",
            COUNT,
            "mdi:database-remove",
            SensorStateClass.TOTAL_INCREASING,
        ),
        ATTR_CACHE_HITRATE: ("Cache Hit Rate", PERCENTAGE, "mdi:gauge", SensorStateClass.MEASUREMENT),
        ATTR_CPU: ("CPU Usage", PERCENTAGE, "mdi:cpu-64-bit", SensorStateClass.MEASUREMENT),
        ATTR_UPTIME: ("Uptime", UnitOfTime.SECONDS, "mdi:timer-outline", SensorStateClass.MEASUREMENT),
        # Rate sensors (rounded to whole units by coordinators)
        ATTR_REQ_PER_HOUR: ("Requests per Hour (last hour)", "req/h", "mdi:chart-line", SensorStateClass.MEASUREMENT),
        ATTR_REQ_PER_DAY: (
            "Requests per Day (last 24h)", "req/d", "mdi:chart-areaspline", SensorStateClass.MEASUREMENT
        ),
        ATTR_SECURITY_STATUS: ("Security Status", None, "mdi:shield-check-outline", None),
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
                is_group=is_group,
            )
        )

    async_add_entities(sensors)

    if coordinator and include_filter_sensors:
        known_rules: set[str] = set()

        @callback
        def _async_sync_filtering_rules() -> None:
            if not coordinator.data:
                return
            rules = coordinator.data.get(ATTR_FILTERING_RULES)
            if not isinstance(rules, dict):
                return

            new_entities: list[DnsdistFilteringRuleSensor] = []
            for slug in rules:
                if slug in known_rules:
                    continue
                entity = DnsdistFilteringRuleSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    rule_slug=slug,
                    is_group=is_group,
                )
                known_rules.add(slug)
                new_entities.append(entity)

            if new_entities:
                _LOGGER.debug(
                    "[dnsdist] Adding filtering rule sensors for %s: %s",
                    getattr(coordinator, "_name", "dnsdist"),
                    [entity._slug for entity in new_entities],
                )
                async_add_entities(new_entities)

        _async_sync_filtering_rules()
        entry.async_on_unload(coordinator.async_add_listener(_async_sync_filtering_rules))

        # Also sync dynamic rules (dynblocks)
        # Track slug -> entity mapping so we can remove expired dynblocks
        dynamic_entities: dict[str, DnsdistDynamicRuleSensor] = {}

        @callback
        def _async_sync_dynamic_rules() -> None:
            if not coordinator.data:
                return
            rules = coordinator.data.get(ATTR_DYNAMIC_RULES)
            if not isinstance(rules, dict):
                rules = {}

            current_slugs = set(rules.keys())
            known_slugs = set(dynamic_entities.keys())

            # Remove entities for expired dynblocks
            expired_slugs = known_slugs - current_slugs
            ent_reg = er.async_get(hass)
            for slug in expired_slugs:
                entity = dynamic_entities.pop(slug, None)
                if entity:
                    _LOGGER.debug(
                        "[dnsdist] Removing expired dynamic rule sensor for %s: %s",
                        getattr(coordinator, "_name", "dnsdist"),
                        slug,
                    )
                    # Remove from entity registry to prevent restoration after restart
                    if entity.entity_id and ent_reg.async_get(entity.entity_id):
                        ent_reg.async_remove(entity.entity_id)
                    else:
                        hass.async_create_task(entity.async_remove())

            # Add new entities
            new_entities: list[DnsdistDynamicRuleSensor] = []
            for slug in rules:
                if slug in dynamic_entities:
                    continue
                entity = DnsdistDynamicRuleSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    rule_slug=slug,
                    is_group=is_group,
                )
                dynamic_entities[slug] = entity
                new_entities.append(entity)

            if new_entities:
                _LOGGER.debug(
                    "[dnsdist] Adding dynamic rule sensors for %s: %s",
                    getattr(coordinator, "_name", "dnsdist"),
                    [entity._slug for entity in new_entities],
                )
                async_add_entities(new_entities)

        _async_sync_dynamic_rules()
        entry.async_on_unload(coordinator.async_add_listener(_async_sync_dynamic_rules))


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
        val = self.coordinator.data.get(self._key) if self.coordinator.data else None

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
            attrs["status_code"] = SECURITY_STATUS_CODE.get(status, 0)
            attrs["status_label"] = SECURITY_STATUS_LABEL.get(status, "Unknown")

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
        return build_device_info(self.coordinator, self._is_group)


class DnsdistFilteringRuleSensor(CoordinatorEntity, SensorEntity):
    """Sensor tracking matches for a dnsdist filtering rule."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = COUNT

    def __init__(
        self,
        *,
        coordinator,
        entry_id: str,
        rule_slug: str,
        is_group: bool,
    ) -> None:
        super().__init__(coordinator)
        self._slug = rule_slug
        self._is_group = is_group
        self._attr_unique_id = f"{entry_id}:filtering_rule:{rule_slug}"

    def _rule_data(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        rules = data.get(ATTR_FILTERING_RULES, {}) if isinstance(data, dict) else {}
        if isinstance(rules, dict):
            return rules.get(self._slug, {})
        return {}

    @property
    def name(self) -> str:
        host = getattr(self.coordinator, "_name", "dnsdist")
        rule = self._rule_data()
        rule_name = str(rule.get("name") or "Unnamed Rule").strip()
        if not rule_name:
            rule_name = "Unnamed Rule"
        return f"{host} Filter {rule_name}".strip()

    @property
    def native_value(self):
        rule = self._rule_data()
        matches = rule.get("matches")
        try:
            if isinstance(matches, bool):
                return int(matches)
            if isinstance(matches, (int, float)):
                return int(matches)
            if isinstance(matches, str):
                return int(float(matches))
        except (TypeError, ValueError):
            return None
        if matches is None:
            return 0 if rule else None
        return matches

    @property
    def icon(self) -> str | None:
        """Return a status icon based on match counts."""

        value = self.native_value
        if value in (0, 0.0):
            return "mdi:filter-check-outline"
        if isinstance(value, (int, float)) and value <= 0:
            return "mdi:filter-check-outline"
        return "mdi:filter"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rule = self._rule_data()
        attrs: dict[str, Any] = {}
        for key in ("id", "uuid", "action", "rule", "type", "enabled", "bypass"):
            if key in rule and rule[key] is not None:
                attrs[key] = rule[key]
        sources = rule.get("sources")
        if isinstance(sources, dict) and sources:
            attrs["sources"] = sources
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self.coordinator, self._is_group)


class DnsdistDynamicRuleSensor(CoordinatorEntity, SensorEntity):
    """Sensor tracking blocks for a dnsdist dynamic rule (dynblock)."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = COUNT

    def __init__(
        self,
        *,
        coordinator,
        entry_id: str,
        rule_slug: str,
        is_group: bool,
    ) -> None:
        super().__init__(coordinator)
        self._slug = rule_slug
        self._is_group = is_group
        self._attr_unique_id = f"{entry_id}:dynamic_rule:{rule_slug}"

    def _rule_data(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        rules = data.get(ATTR_DYNAMIC_RULES, {}) if isinstance(data, dict) else {}
        if isinstance(rules, dict):
            return rules.get(self._slug, {})
        return {}

    @property
    def name(self) -> str:
        host = getattr(self.coordinator, "_name", "dnsdist")
        rule = self._rule_data()
        network = str(rule.get("network") or "Unknown").strip()
        if not network:
            network = "Unknown"
        return f"{host} Dynblock {network}".strip()

    @property
    def native_value(self):
        rule = self._rule_data()
        blocks = rule.get("blocks")
        try:
            if isinstance(blocks, bool):
                return int(blocks)
            if isinstance(blocks, (int, float)):
                return int(blocks)
            if isinstance(blocks, str):
                return int(float(blocks))
        except (TypeError, ValueError):
            return None
        if blocks is None:
            return 0 if rule else None
        return blocks

    @property
    def icon(self) -> str | None:
        """Return a status icon based on block counts."""
        value = self.native_value
        if value in (0, 0.0):
            return "mdi:shield-check-outline"
        if isinstance(value, (int, float)) and value <= 0:
            return "mdi:shield-check-outline"
        return "mdi:shield-alert"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rule = self._rule_data()
        attrs: dict[str, Any] = {}
        for key in ("network", "reason", "action", "seconds", "ebpf", "warning"):
            if key in rule and rule[key] is not None:
                attrs[key] = rule[key]
        # Add human-readable time remaining
        seconds = rule.get("seconds")
        if isinstance(seconds, (int, float)) and seconds > 0:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            if mins > 0:
                attrs["time_remaining"] = f"{mins}m {secs}s"
            else:
                attrs["time_remaining"] = f"{secs}s"
        sources = rule.get("sources")
        if isinstance(sources, dict) and sources:
            attrs["sources"] = sources
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self.coordinator, self._is_group)
