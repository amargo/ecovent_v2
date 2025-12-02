"""Config flow for EcoVent_v2 integration."""
from __future__ import annotations

import logging
from typing import Any

from ecoventv2 import Fan
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# adjust the data schema to the data that you need
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS, default="<broadcast>"): str,
        vol.Optional(CONF_PORT, default=4000): int,
        vol.Optional(CONF_DEVICE_ID, default="DEFAULT_DEVICEID"): str,
        vol.Required(CONF_PASSWORD, default="1111"): str,
        vol.Optional(CONF_NAME, default="Vento Expert Fan"): str,
    }
)


class VentoHub:
    """Vento Hub Class."""

    def __init__(self, host: str, port: int, fan_id: str, name: str) -> None:
        """Initialize."""
        self.host = host
        self.port = port
        self.fan_id = fan_id
        self.fan = None
        self.name = name

    def authenticate(self, password: str) -> bool:
        """Authenticate."""
        _LOGGER.debug(
            "Authenticating Vento fan at %s:%s with device_id=%s",
            self.host,
            self.port,
            self.fan_id,
        )
        self.fan = Fan(self.host, password, self.fan_id, self.name, self.port)
        init_ok = self.fan.init_device()
        self.fan_id = self.fan.id
        self.name = self.name + " " + self.fan_id
        if not init_ok or self.fan_id == "DEFAULT_DEVICEID":
            _LOGGER.error(
                "Authentication failed for Vento fan at %s:%s (device_id=%s)",
                self.host,
                self.port,
                self.fan_id,
            )
            return False
        _LOGGER.info(
            "Authenticated Vento fan %s with id %s at %s:%s",
            self.name,
            self.fan_id,
            self.host,
            self.port,
        )
        return True


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # await hass.async_add_executor_job(
    #     your_validate_func, data["username"], data["password"]
    # )

    hub = VentoHub(
        data[CONF_IP_ADDRESS], data[CONF_PORT], data[CONF_DEVICE_ID], data[CONF_NAME]
    )

    _LOGGER.debug(
        "Validating EcoVent_v2 config for host=%s, port=%s, device_id=%s, name=%s",
        data[CONF_IP_ADDRESS],
        data[CONF_PORT],
        data[CONF_DEVICE_ID],
        data[CONF_NAME],
    )

    try:
        authenticated = await hass.async_add_executor_job(
            hub.authenticate,
            data[CONF_PASSWORD],
        )
    except OSError as err:
        _LOGGER.error(
            "Error connecting to Vento fan at %s:%s during validation: %s",
            data[CONF_IP_ADDRESS],
            data[CONF_PORT],
            err,
        )
        raise CannotConnect from err
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.exception(
            "Unexpected error while validating Vento fan at %s:%s",
            data[CONF_IP_ADDRESS],
            data[CONF_PORT],
        )
        raise CannotConnect from err

    if not authenticated:
        raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": hub.name, "id": hub.fan_id}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoVent_v2."""

    VERSION = 1

    def __init__(self):
        """Initialite ConfigFlow."""
        self._fan = Fan(
            "<broadcast>", "1111", "DEFAULT_DEVICEID", "Vento Express", 4000
        )

    def _probe_ip(self, ip, user_input, unique_ids):
        """Probe a single IP for a Vento fan.

        This runs in an executor and must not use async APIs.
        """
        self._fan.host = ip
        self._fan.id = user_input[CONF_DEVICE_ID]
        self._fan.password = user_input[CONF_PASSWORD]
        self._fan.name = user_input[CONF_NAME]
        self._fan.port = user_input[CONF_PORT]
        self._fan.init_device()
        if self._fan.id not in unique_ids:
            return True, self._fan.id
        return False, self._fan.id

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            if user_input[CONF_IP_ADDRESS] == "<broadcast>":
                ip = None
                _LOGGER.debug("Starting broadcast search for Vento fans")
                ips = await self.hass.async_add_executor_job(
                    self._fan.search_devices,
                    "0.0.0.0",
                )
                # ips = ["10.94.0.105", "10.94.0.106", "10.94.0.107", "10.94.0.108"]
                if not ips:
                    _LOGGER.error("No Vento fans found via broadcast discovery")
                    raise NoDevicesFound
                unique_ids = []
                for entry in self._async_current_entries(include_ignore=True):
                    unique_ids.append(entry.unique_id)
                _LOGGER.debug("Discovered Vento fans at IPs: %s", ips)
                for ip in ips:
                    _LOGGER.debug("Probing Vento fan at %s", ip)
                    success, fan_id = await self.hass.async_add_executor_job(
                        self._probe_ip,
                        ip,
                        user_input,
                        unique_ids,
                    )
                    if success:
                        user_input[CONF_IP_ADDRESS] = ip
                        _LOGGER.info(
                            "Selected Vento fan at %s with id %s for configuration",
                            ip,
                            fan_id,
                        )
                        break
                if user_input[CONF_IP_ADDRESS] == "<broadcast>":
                    _LOGGER.error(
                        "All discovered Vento fans are already configured: %s",
                        unique_ids,
                    )
                    raise AllDevicesConfigured

            info = await validate_input(self.hass, user_input)
            await self.async_set_unique_id(info["id"])
            self._abort_if_unique_id_configured()
        except NoDevicesFound:
            errors["base"] = "no_devices_found"
        except AllDevicesConfigured:
            errors["base"] = "all_devices_configured"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoDevicesFound(exceptions.HomeAssistantError):
    """Error to indicate no devices were found during broadcast discovery."""


class AllDevicesConfigured(exceptions.HomeAssistantError):
    """Error to indicate all discovered devices are already configured."""
