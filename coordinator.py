"""DataUpdateCoordinator for OpenEnergy."""

from __future__ import annotations

from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import get_health
from .const import CONF_HEALTH_URL, DATA_OE_TOKEN, DEFAULT_HEALTH_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class OpenEnergyCoordinator(DataUpdateCoordinator):
    """Class to manage fetching OpenEnergy data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize global OpenEnergy data updater."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.config_entry = entry

    async def _async_update_data(self) -> dict:
        """Fetch data from API endpoint.

        Returns:
            dict: The status data including health check result.
        """
        health_url = self.config_entry.data.get(CONF_HEALTH_URL, DEFAULT_HEALTH_URL)
        
        start_time = time.monotonic()
        ok, details = await get_health(self.hass, health_url)
        latency = (time.monotonic() - start_time) * 1000  # in ms

        if not ok:
            # We don't raise UpdateFailed for health check failure to keep sensors available
            # but marking them as issue if needed.
            # However, for a binary_sensor connectivity, we might just want to return the state.
            pass

        return {
            "health_ok": ok,
            "health_details": details,
            "latency_ms": round(latency, 2),
            "has_token": DATA_OE_TOKEN in self.config_entry.data,
        }
