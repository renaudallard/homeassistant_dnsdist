"""Config flow and options for PowerDNS dnsdist integration."""

from __future__ import annotations
import logging
import aiohttp
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_API_KEY,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    CONF_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


# ============================================================
# Helper: Validate connection
# ============================================================

async def _validate_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    api_key: str,
    use_https: bool,
    verify_ssl: bool,
) -> bool:
    """Try connecting to the dnsdist API."""
    protocol = "https" if use_https else "http"
    url = f"{protocol}://{host}:{port}/api/v1/servers/localhost/statistics"
    headers = {"X-API-Key": api_key} if api_key else {}
    _LOGGER.debug("Testing dnsdist connection for %s:%s", host, port)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=verify_ssl, timeout=5) as resp:
                if resp.status == 200:
                    _LOGGER.debug("dnsdist connection succeeded for %s:%s", host, port)
                    return True
                _LOGGER.warning("dnsdist API returned HTTP %s for %s:%s", resp.status, host, port)
                return False
    except Exception as err:
        _LOGGER.error("dnsdist connection error for %s:%s: %s", host, port, err)
        return False


# ============================================================
# Config Flow
# ============================================================

class DnsdistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle dnsdist configuration flow."""

    VERSION = 4  # bumped for secure storage

    async def async_step_user(self, user_input: dict | None = None):
        """First step: choose to add a host or group."""
        if user_input is not None:
            if user_input["mode"] == "add_hub":
                return await self.async_step_add_hub()
            if user_input["mode"] == "add_group":
                return await self.async_step_add_group()

        schema = vol.Schema(
            {
                vol.Required("mode"): vol.In(
                    {
                        "add_hub": "Add dnsdist Host",
                        "add_group": "Add dnsdist Group",
                    }
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    # ------------------------------------------------------------
    # Add Host
    # ------------------------------------------------------------

    async def async_step_add_hub(self, user_input: dict | None = None):
        """Configure a dnsdist host."""
        errors = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            api_key = user_input.get(CONF_API_KEY, "")
            use_https = user_input.get(CONF_USE_HTTPS, False)
            verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, 30)

            valid = await _validate_connection(
                self.hass, host, port, api_key, use_https, verify_ssl
            )
            if not valid:
                errors["base"] = "cannot_connect"

            if not errors:
                entry_data = {
                    CONF_NAME: name,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_USE_HTTPS: use_https,
                    CONF_VERIFY_SSL: verify_ssl,
                    CONF_UPDATE_INTERVAL: update_interval,
                    "is_group": False,
                }

                # Store API key securely
                if api_key:
                    self.add_secret(CONF_API_KEY, api_key)

                _LOGGER.debug("Creating new dnsdist host entry: %s", entry_data)
                return self.async_create_entry(title=name, data=entry_data)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=8083): int,
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Optional(CONF_USE_HTTPS, default=False): bool,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(
                    int, vol.Range(min=10, max=600)
                ),
            }
        )

        return self.async_show_form(step_id="add_hub", data_schema=schema, errors=errors)

    # ------------------------------------------------------------
    # Add Group
    # ------------------------------------------------------------

    async def async_step_add_group(self, user_input: dict | None = None):
        """Configure a dnsdist group."""
        errors = {}

        all_entries = [
            (e.data.get(CONF_NAME), e.data.get("is_group", False))
            for e in self.hass.config_entries.async_entries(DOMAIN)
        ]
        available_hosts = [n for n, is_group in all_entries if n and not is_group]

        if not available_hosts:
            errors["base"] = "no_hosts"
            _LOGGER.warning("No dnsdist hosts available to group")
            return self.async_show_form(
                step_id="add_group",
                errors=errors,
                description_placeholders={
                    "message": "You must add at least one dnsdist host before creating a group."
                },
            )

        if user_input is not None:
            group_name = user_input.get(CONF_NAME)
            members = user_input.get("members", [])
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, 30)

            if not group_name:
                errors["name"] = "required"
            elif not members:
                errors["members"] = "no_members"
            elif any(
                e.data.get(CONF_NAME) == group_name
                for e in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors["name"] = "duplicate"

            if not errors:
                _LOGGER.debug("Creating dnsdist group '%s' with members %s", group_name, members)
                return self.async_create_entry(
                    title=group_name,
                    data={
                        CONF_NAME: group_name,
                        "is_group": True,
                        "members": members,
                        CONF_UPDATE_INTERVAL: update_interval,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required("members", default=[]): cv.multi_select(available_hosts),
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(
                    int, vol.Range(min=10, max=600)
                ),
            }
        )

        return self.async_show_form(step_id="add_group", data_schema=schema, errors=errors)

    # ------------------------------------------------------------
    # Options Flow entrypoint
    # ------------------------------------------------------------

    @staticmethod
    @config_entries.HANDLERS.register(DOMAIN)
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return DnsdistOptionsFlowHandler(config_entry)


# ============================================================
# Options Flow
# ============================================================

class DnsdistOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for dnsdist."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry
        self.is_group = config_entry.data.get("is_group", False)
        self._name = config_entry.data.get(CONF_NAME)
        self._members = config_entry.data.get("members", [])
        self._update_interval = config_entry.data.get(CONF_UPDATE_INTERVAL, 30)

    async def async_step_init(self, user_input: dict | None = None):
        """Manage the options for dnsdist entry."""
        errors = {}
        hass = self.hass

        if self.is_group:
            all_entries = hass.config_entries.async_entries(DOMAIN)
            available_hosts = [
                e.data.get(CONF_NAME)
                for e in all_entries
                if not e.data.get("is_group")
            ]

            if user_input is not None:
                name = user_input["name"].strip()
                members = user_input.get("members", [])
                update_interval = user_input.get(CONF_UPDATE_INTERVAL, 30)

                if not name:
                    errors["name"] = "required"
                elif not members:
                    errors["members"] = "no_members"

                if not errors:
                    new_data = dict(self.config_entry.data)
                    new_data.update(
                        {
                            CONF_NAME: name,
                            "members": members,
                            CONF_UPDATE_INTERVAL: update_interval,
                        }
                    )
                    hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                    _LOGGER.info("Updated dnsdist group '%s' with members %s", name, members)
                    return self.async_create_entry(title="", data={})

            schema = vol.Schema(
                {
                    vol.Required("name", default=self._name): str,
                    vol.Required("members", default=self._members): cv.multi_select(available_hosts),
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=self._update_interval
                    ): vol.All(int, vol.Range(min=10, max=600)),
                }
            )

            return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

        # Host configuration edit
        if user_input is not None:
            new_interval = user_input.get(CONF_UPDATE_INTERVAL, self._update_interval)
            new_data = dict(self.config_entry.data)
            new_data[CONF_UPDATE_INTERVAL] = new_interval
            hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=self._update_interval
                ): vol.All(int, vol.Range(min=10, max=600))
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
