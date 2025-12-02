"""VentoUpdateCoordinator class."""

# from __future__ import annotations
from datetime import timedelta
import logging

from ecoventv2 import Fan

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class VentoFanDataUpdateCoordinator(DataUpdateCoordinator):
    """Class for Vento Fan Update Coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigEntry,
    ) -> None:
        """Initialize global Vento data updater."""
        self._host = config.data[CONF_IP_ADDRESS]
        self._port = config.data[CONF_PORT]
        self._device_id = config.data[CONF_DEVICE_ID]
        self._name = config.data[CONF_NAME]

        _LOGGER.debug(
            "Initializing Vento fan coordinator for %s (host=%s, port=%s, device_id=%s)",
            self._name,
            self._host,
            self._port,
            self._device_id,
        )

        self._fan = Fan(
            self._host,
            config.data[CONF_PASSWORD],
            self._device_id,
            self._name,
            self._port,
        )

        try:
            init_ok = self._fan.init_device()
        except Exception as err:
            _LOGGER.error(
                "Failed to initialize Vento fan at %s:%s (device_id=%s, name=%s): %s",
                self._host,
                self._port,
                self._device_id,
                self._name,
                err,
            )
            raise ConfigEntryNotReady(
                f"Failed to initialize Vento fan at {self._host}:{self._port}"
            ) from err

        fan_id = getattr(self._fan, "id", None)
        if not init_ok or not fan_id or fan_id == "DEFAULT_DEVICEID":
            _LOGGER.error(
                "Could not detect Vento fan ID at %s:%s (configured device_id=%s, name=%s). "
                "Please check IP address, password and network connectivity.",
                self._host,
                self._port,
                self._device_id,
                self._name,
            )
            raise ConfigEntryNotReady(
                f"Could not detect Vento fan ID at {self._host}:{self._port}"
            )

        _LOGGER.info(
            "Initialized Vento fan %s with id %s at %s:%s",
            self._name,
            fan_id,
            self._host,
            self._port,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            await self.hass.async_add_executor_job(self._fan.update)
        except Exception as err:
            _LOGGER.error(
                "Error updating Vento fan at %s:%s (id=%s): %s",
                self._host,
                self._port,
                getattr(self._fan, "id", None),
                err,
            )
            raise UpdateFailed(f"Error communicating with Vento fan: {err}") from err
