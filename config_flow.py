"""Config flow for OpenEnergy integration."""
from __future__ import annotations
from homeassistant.helpers import config_entry_oauth2_flow
from .const import DOMAIN, LOGGER


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle OpenEnergy OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self):
        """Return logger."""
        return LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": "openid email profile offline_access"}

    async def async_step_user(self, user_input: dict | None = None) -> dict:
        """Handle a flow initiated by the user."""
        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data: dict) -> dict:
        """Create an entry for the flow, or update existing entry."""
        return self.async_create_entry(title="OpenEnergy", data=data)

