# 202510231130
"""Options flow for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_IS_GROUP,
    CONF_MEMBERS,
    CONF_INCLUDE_FILTER_SENSORS,
    CONF_REMOVE_DISABLED_FILTER_SENSORS,
)


_LOGGER = logging.getLogger(__name__)

class DnsdistOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle dnsdist options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize dnsdist options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        data = self.config_entry.data
        is_group = bool(data.get(CONF_IS_GROUP))
        name = data.get(CONF_NAME, self.config_entry.title)
        update_interval = int(data.get(CONF_UPDATE_INTERVAL, 30))
        members = list(data.get(CONF_MEMBERS, []))
        include_filter_sensors = bool(
            data.get(CONF_INCLUDE_FILTER_SENSORS, bool(is_group))
        )

        # Build available hosts from other host entries
        entries = [e for e in self.hass.config_entries.async_entries(DOMAIN) if not e.data.get(CONF_IS_GROUP)]
        available_hosts = sorted({e.data.get(CONF_NAME, e.title) for e in entries})

        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = dict(data)
            # Update common options
            new_interval = user_input.get(CONF_UPDATE_INTERVAL, update_interval)
            new_data[CONF_UPDATE_INTERVAL] = int(new_interval)

            new_include_filters = bool(
                user_input.get(CONF_INCLUDE_FILTER_SENSORS, include_filter_sensors)
            )
            new_data[CONF_INCLUDE_FILTER_SENSORS] = new_include_filters

            remove_on_disable = bool(
                user_input.get(
                    CONF_REMOVE_DISABLED_FILTER_SENSORS,
                    True,
                )
            )

            if (
                include_filter_sensors
                and not new_include_filters
                and remove_on_disable
            ):
                _remove_filtering_rule_entities(
                    self.hass, self.config_entry.entry_id
                )

            # Update name (we'll update entry title)
            new_name = user_input.get(CONF_NAME, name)
            if isinstance(new_name, str) and new_name:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=new_name
                )
                new_data[CONF_NAME] = new_name

            # Update group-specific members
            if is_group:
                new_members = user_input.get(CONF_MEMBERS, members)
                if not new_members:
                    errors["base"] = "no_members"
                else:
                    new_data[CONF_MEMBERS] = list(new_members)

            if not errors:
                self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                return self.async_create_entry(title="", data={})

        # Schemas
        if is_group:
            # Allow selecting any available host names (multi-select)
            schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default=name): str,
                    vol.Required(
                        CONF_MEMBERS,
                        default=members,
                    ): cv.multi_select(sorted(available_hosts)),
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=update_interval
                    ): vol.All(int, vol.Range(min=10, max=600)),
                    vol.Optional(
                        CONF_INCLUDE_FILTER_SENSORS, default=include_filter_sensors
                    ): bool,
                    vol.Optional(
                        CONF_REMOVE_DISABLED_FILTER_SENSORS,
                        default=True,
                    ): bool,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default=name): str,
                    vol.Optional(CONF_UPDATE_INTERVAL, default=update_interval): vol.All(int, vol.Range(min=10, max=600)),
                    vol.Optional(
                        CONF_INCLUDE_FILTER_SENSORS, default=include_filter_sensors
                    ): bool,
                    vol.Optional(
                        CONF_REMOVE_DISABLED_FILTER_SENSORS,
                        default=True,
                    ): bool,
                }
            )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


def _remove_filtering_rule_entities(hass, entry_id: str) -> None:
    """Delete filtering rule sensor entities for an entry."""

    entity_registry = er.async_get(hass)
    filter_unique_prefix = f"{entry_id}:filtering_rule:"
    to_remove = [
        er_entry.entity_id
        for er_entry in list(entity_registry.entities.values())
        if er_entry.config_entry_id == entry_id
        and er_entry.unique_id.startswith(filter_unique_prefix)
    ]

    if to_remove:
        _LOGGER.debug(
            "[dnsdist] Removing filtering rule sensors on disable: %s",
            to_remove,
        )

    for entity_id in to_remove:
        entity_registry.async_remove(entity_id)


@callback
def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    """Return the options flow handler."""
    return DnsdistOptionsFlowHandler(config_entry)
