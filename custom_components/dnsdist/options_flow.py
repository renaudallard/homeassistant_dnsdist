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

"""Options flow for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_MEMBERS,
    CONF_INCLUDE_FILTER_SENSORS,
    CONF_REMOVE_DISABLED_FILTER_SENSORS,
)
from .utils import is_group_entry, name_is_taken


_LOGGER = logging.getLogger(__name__)


class DnsdistOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle dnsdist options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        data = self.config_entry.data
        is_group = is_group_entry(self.config_entry)
        name = data.get(CONF_NAME, self.config_entry.title)
        update_interval = int(data.get(CONF_UPDATE_INTERVAL, 30))
        members = list(data.get(CONF_MEMBERS, []))
        include_filter_sensors = bool(data.get(CONF_INCLUDE_FILTER_SENSORS, bool(is_group)))

        # Build available hosts from other host entries
        entries = [e for e in self.hass.config_entries.async_entries(DOMAIN) if not is_group_entry(e)]
        available_hosts = sorted({e.data.get(CONF_NAME, e.title) for e in entries})

        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = dict(data)
            # Update common options
            new_interval = user_input.get(CONF_UPDATE_INTERVAL, update_interval)
            new_data[CONF_UPDATE_INTERVAL] = int(new_interval)

            new_include_filters = bool(user_input.get(CONF_INCLUDE_FILTER_SENSORS, include_filter_sensors))
            new_data[CONF_INCLUDE_FILTER_SENSORS] = new_include_filters

            remove_on_disable = bool(
                user_input.get(
                    CONF_REMOVE_DISABLED_FILTER_SENSORS,
                    True,
                )
            )

            # Update name (the entry title follows it below)
            new_name = user_input.get(CONF_NAME, name)
            if isinstance(new_name, str) and new_name:
                new_data[CONF_NAME] = new_name
            else:
                new_name = name

            if new_name != name and name_is_taken(self.hass, new_name, entry_id=self.config_entry.entry_id):
                errors[CONF_NAME] = "duplicate"

            # Update group-specific members
            if is_group:
                new_members = user_input.get(CONF_MEMBERS, members)
                if not new_members:
                    errors["base"] = "no_members"
                else:
                    new_data[CONF_MEMBERS] = list(new_members)

            if not errors:
                # Only once the form is accepted, or a rejected submission
                # would delete the sensors anyway.
                if include_filter_sensors and not new_include_filters and remove_on_disable:
                    _remove_rule_entities(self.hass, self.config_entry.entry_id)

                if not is_group and new_name != name:
                    _rename_group_members(self.hass, name, new_name)

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                    title=new_data.get(CONF_NAME, self.config_entry.title),
                )
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
                    vol.Optional(CONF_UPDATE_INTERVAL, default=update_interval): vol.All(
                        int, vol.Range(min=10, max=600)
                    ),
                    vol.Optional(CONF_INCLUDE_FILTER_SENSORS, default=include_filter_sensors): bool,
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
                    vol.Optional(CONF_UPDATE_INTERVAL, default=update_interval): vol.All(
                        int, vol.Range(min=10, max=600)
                    ),
                    vol.Optional(CONF_INCLUDE_FILTER_SENSORS, default=include_filter_sensors): bool,
                    vol.Optional(
                        CONF_REMOVE_DISABLED_FILTER_SENSORS,
                        default=True,
                    ): bool,
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )


def _rename_group_members(hass, old_name: str, new_name: str) -> None:
    """Carry a host rename into the groups that list it.

    Group membership is stored as display names, so a renamed host silently
    falls out of every group it belonged to unless the lists follow it.
    """

    for entry in hass.config_entries.async_entries(DOMAIN):
        if not is_group_entry(entry):
            continue

        members = list(entry.data.get(CONF_MEMBERS, []))
        if old_name not in members:
            continue

        renamed = [new_name if member == old_name else member for member in members]
        _LOGGER.debug("[dnsdist] Group '%s' now points at '%s'", entry.title, new_name)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MEMBERS: renamed})


def _remove_rule_entities(hass, entry_id: str) -> None:
    """Delete the rule sensor entities for an entry.

    The option gates both the filtering rule and the dynblock sensors, so both
    have to go, otherwise the dynblock ones stay behind with nothing left to
    ever remove them.
    """

    entity_registry = er.async_get(hass)
    prefixes = (f"{entry_id}:filtering_rule:", f"{entry_id}:dynamic_rule:")
    to_remove = [
        er_entry.entity_id
        for er_entry in er.async_entries_for_config_entry(entity_registry, entry_id)
        if er_entry.unique_id.startswith(prefixes)
    ]

    if to_remove:
        _LOGGER.debug(
            "[dnsdist] Removing rule sensors on disable: %s",
            to_remove,
        )

    for entity_id in to_remove:
        entity_registry.async_remove(entity_id)
