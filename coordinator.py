"""DataUpdateCoordinator for OpenEnergy."""
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import OpenEnergyApiClient
from .const import DOMAIN, LOGGER

class OpenEnergyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the OpenEnergy API."""

    def __init__(self, hass, entry):
        """Initialize."""
        self.api = OpenEnergyApiClient(hass, entry)

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            return await self.api.get_frp_config()
        except Exception as e:
            LOGGER.exception("Error communicating with API: %s", e)
            raise