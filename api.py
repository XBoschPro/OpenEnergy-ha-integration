"""API for OpenEnergy."""
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# TODO: Replace with the actual API endpoint
API_ENDPOINT = "https://api.openenergy.cloud/v1/frp"

class OpenEnergyApiClient:
    """API client for OpenEnergy."""

    def __init__(self, hass, entry):
        """Initialize the client."""
        self.hass = hass
        self.entry = entry
        self.session = async_get_clientsession(hass)

    async def get_frp_config(self):
        """Get the FRP configuration from the OpenEnergy API."""
        token = self.entry.data["token"]
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        
        response = await self.session.get(API_ENDPOINT, headers=headers)
        response.raise_for_status()
        
        return await response.json()