# 202510231230
"""Config flow and options for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
from typing import Any

import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_API_KEY,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_UPDATE_INTERVAL,
    CONF_MEMBERS,
    CONF_IS_GROUP,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    api_key: str | None,
    use_https: bool,
    verify_ssl: bool,
) -> bool:
    """Try connecting to the dnsdist API."""
    protocol = "https" if use_https else "http"
    url = f"{protocol}://{host}:{port}/api/v1/servers/localhost/statistics"
    headers = {"X-API-Key": api_key} if api_key else {}
    _LOGGER.debug("Testing dnsdist connection for %s:%s", host, port)

    session = async_get_clientsession(hass)

    try:
        async with asyncio.timeout(5):
            async with session.get(url, headers=headers, ssl=verify_ssl) as resp:
                if resp.status == 200:
                    _LOGGER.debug("dnsdist connection succeeded for %s:%s", host, port)
                    return True
                _LOGGER.warning("dnsdist API returned HTTP %s for %s:%s", resp.status, host, port)
                return False
    except Exception as err:
        _LOGGER.error("dnsdist connection error for %s:%s: %s", host, port, err)
        return False


class DnsdistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle dnsdist configuration flow."""

    VERSION = 4  # keep in sync with async_migrate_entry

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """First step: choose to add a host or group."""
        schema = vol.Schema({vol.Required("mode", default="host"): vol.In({"host": "Host", "group": "Group"})})
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=schema)

        if user_input["mode"] == "group":
            return await self.async_step_add_group()
        return await self.async_step_add_hub()

    async def async_step_add_hub(self, user_input: dict[str, Any] | None = None):
        """Add a single dnsdist host."""
        errors: dict[str, str] = {}

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=8083): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Optional(CONF_USE_HTTPS, default=False): bool,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(int, vol.Range(min=10, max=600)),
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="add_hub", data_schema=schema)

        name = user_input[CONF_NAME]
        host = user_input[CONF_HOST]
        port = user_input[CONF_PORT]
        api_key = user_input.get(CONF_API_KEY, "") or None
        use_https = user_input.get(CONF_USE_HTTPS, False)
        verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
        update_interval = user_input.get(CONF_UPDATE_INTERVAL, 30)

        valid = await _validate_connection(self.hass, host, port, api_key, use_https, verify_ssl)
        if not valid:
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(step_id="add_hub", data_schema=schema, errors=errors)

        # NOTE: We store api_key in data. __init__.py will use secure storage if available,
        # and migration can move plaintext to secrets on supported platforms.
        data = {
            CONF_NAME: name,
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_API_KEY: api_key,            # keep for now; may be migrated to secret later
            CONF_USE_HTTPS: use_https,
            CONF_VERIFY_SSL: verify_ssl,
            CONF_UPDATE_INTERVAL: update_interval,
            CONF_IS_GROUP: False,
        }

        return self.async_create_entry(title=name, data=data)

    async def async_step_add_group(self, user_input: dict[str, Any] | None = None):
        """Add an aggregated group."""
        errors: dict[str, str] = {}

        # Determine available host names from existing host entries
        entries = [e for e in self._async_current_entries() if not e.data.get(CONF_IS_GROUP)]
        available_hosts = {e.data.get(CONF_NAME, e.title) for e in entries}
        if not available_hosts:
            errors["base"] = "no_hosts"

        if user_input is not None and not errors:
            group_name = user_input[CONF_NAME]
            members = user_input.get(CONF_MEMBERS, [])
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, 30)

            if not members:
                errors["base"] = "no_members"

            if not errors:
                return self.async_create_entry(
                    title=group_name,
                    data={
                        CONF_NAME: group_name,
                        CONF_IS_GROUP: True,
                        CONF_MEMBERS: members,
                        CONF_UPDATE_INTERVAL: update_interval,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_MEMBERS, default=[]): cv.multi_select(sorted(available_hosts)),
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(int, vol.Range(min=10, max=600)),
            }
        )

        return self.async_show_form(step_id="add_group", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        from .options_flow import DnsdistOptionsFlowHandler  # lazy import
        return DnsdistOptionsFlowHandler(config_entry)
