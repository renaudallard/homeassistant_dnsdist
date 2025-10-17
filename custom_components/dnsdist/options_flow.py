"""Options flow for PowerDNS dnsdist integration."""

from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN


class DnsdistOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle dnsdist options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize dnsdist options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    "human_readable_uptime",
                    default=current.get("human_readable_uptime", False),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


@callback
def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    """Return the options flow handler."""
    return DnsdistOptionsFlowHandler(config_entry)
