"""Config flow and options for PowerDNS dnsdist integration."""

from __future__ import annotations

import logging
import re
from asyncio import timeout, TimeoutError as AsyncTimeoutError
from typing import Any

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
    CONF_INCLUDE_FILTER_SENSORS,
)

_LOGGER = logging.getLogger(__name__)

# Regex patterns for hostname/IP validation
# Hostname pattern: RFC 1123 compliant (letters, digits, hyphens, dots)
_HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)"  # Total length limit
    r"(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)*"  # Subdomains
    r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)$"  # Final label
)

# IPv4 pattern: 0-255.0-255.0-255.0-255
_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)

# IPv6 pattern: simplified pattern for common IPv6 formats
_IPV6_PATTERN = re.compile(
    r"^(?:"
    r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|"  # Full format
    r"(?:[0-9a-fA-F]{1,4}:){1,7}:|"  # With trailing ::
    r"(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"  # :: in middle
    r"::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}|"  # :: at start
    r"::|"  # Loopback shorthand
    r"::1"  # Loopback
    r")$"
)


def validate_host(host: str) -> str:
    """Validate hostname or IP address format."""
    if not host or not isinstance(host, str):
        raise vol.Invalid("Host must be a non-empty string")

    host = host.strip()

    # Check if it's a valid IPv4 address
    if _IPV4_PATTERN.match(host):
        return host

    # Check if it's a valid IPv6 address (with or without brackets)
    host_unwrapped = host.strip("[]")
    if _IPV6_PATTERN.match(host_unwrapped):
        return host

    # Reject strings that look like malformed IPv4 addresses
    # (all-numeric labels separated by dots)
    if re.match(r"^[\d.]+$", host):
        raise vol.Invalid(
            f"Invalid IPv4 address format: '{host}'. "
            "IPv4 addresses must have exactly 4 octets (0-255) separated by dots"
        )

    # Check if it's a valid hostname
    if _HOSTNAME_PATTERN.match(host):
        return host

    raise vol.Invalid(
        f"Invalid host format: '{host}'. "
        "Must be a valid hostname, IPv4 address, or IPv6 address"
    )


async def _validate_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    api_key: str | None,
    use_https: bool,
    verify_ssl: bool,
) -> bool:
    """Try connecting to the dnsdist API and validate response structure."""
    protocol = "https" if use_https else "http"
    url = f"{protocol}://{host}:{port}/api/v1/servers/localhost/statistics"
    headers = {"X-API-Key": api_key} if api_key else {}
    _LOGGER.debug("Testing dnsdist connection for %s:%s", host, port)

    session = async_get_clientsession(hass)

    try:
        async with timeout(5):
            async with session.get(url, headers=headers, ssl=verify_ssl) as resp:
                if resp.status != 200:
                    _LOGGER.warning("dnsdist API returned HTTP %s for %s:%s", resp.status, host, port)
                    return False

                # Validate JSON response structure
                try:
                    data = await resp.json()
                except Exception as json_err:
                    _LOGGER.warning(
                        "dnsdist API response is not valid JSON for %s:%s: %s",
                        host, port, json_err
                    )
                    return False

                # Verify this is a dnsdist statistics response
                # dnsdist statistics typically include these core fields
                required_fields = ["queries", "responses"]
                if not isinstance(data, dict):
                    _LOGGER.warning(
                        "dnsdist API response is not a dictionary for %s:%s",
                        host, port
                    )
                    return False

                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    _LOGGER.warning(
                        "dnsdist API response missing required fields %s for %s:%s. "
                        "This may not be a dnsdist endpoint.",
                        missing_fields, host, port
                    )
                    return False

                _LOGGER.debug(
                    "dnsdist connection validated successfully for %s:%s "
                    "(found %d statistics fields)",
                    host, port, len(data)
                )
                return True

    except AsyncTimeoutError:
        _LOGGER.error("dnsdist connection timeout for %s:%s", host, port)
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
                vol.Required(CONF_HOST): vol.All(str, validate_host),
                vol.Required(CONF_PORT, default=8083): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Optional(CONF_USE_HTTPS, default=False): bool,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(int, vol.Range(min=10, max=600)),
                vol.Optional(CONF_INCLUDE_FILTER_SENSORS, default=False): bool,
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
        include_filter_sensors = bool(user_input.get(CONF_INCLUDE_FILTER_SENSORS, False))

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
            CONF_INCLUDE_FILTER_SENSORS: include_filter_sensors,
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
            include_filter_sensors = bool(
                user_input.get(CONF_INCLUDE_FILTER_SENSORS, True)
            )

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
                        CONF_INCLUDE_FILTER_SENSORS: include_filter_sensors,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_MEMBERS, default=[]): cv.multi_select(sorted(available_hosts)),
                vol.Optional(CONF_UPDATE_INTERVAL, default=30): vol.All(int, vol.Range(min=10, max=600)),
                vol.Optional(CONF_INCLUDE_FILTER_SENSORS, default=True): bool,
            }
        )

        return self.async_show_form(step_id="add_group", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        from .options_flow import DnsdistOptionsFlowHandler  # lazy import
        return DnsdistOptionsFlowHandler(config_entry)
