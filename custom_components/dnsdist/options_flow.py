# 202510231130
"""Options flow for PowerDNS dnsdist integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_IS_GROUP,
    CONF_MEMBERS,
)

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

        # Build available hosts from other host entries
        entries = [e for e in self.hass.config_entries.async_entries(DOMAIN) if not e.data.get(CONF_IS_GROUP)]
        available_hosts = sorted({e.data.get(CONF_NAME, e.title) for e in entries})

        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = dict(data)
            # Update common options
            new_interval = user_input.get(CONF_UPDATE_INTERVAL, update_interval)
            new_data[CONF_UPDATE_INTERVAL] = int(new_interval)

            # Update name (we'll update entry title)
            new_name = user_input.get(CONF_NAME, name)
            if isinstance(new_name, str) and new_name:
                await self.hass.config_entries.async_update_entry(self.config_entry, title=new_name)
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
                    vol.Required(CONF_MEMBERS, default=members): list,
                    vol.Optional(CONF_UPDATE_INTERVAL, default=update_interval): vol.All(int, vol.Range(min=10, max=600)),
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default=name): str,
                    vol.Optional(CONF_UPDATE_INTERVAL, default=update_interval): vol.All(int, vol.Range(min=10, max=600)),
                }
            )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


@callback
def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    """Return the options flow handler."""
    return DnsdistOptionsFlowHandler(config_entry)
