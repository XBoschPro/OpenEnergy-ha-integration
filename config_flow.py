"""Config flow for OpenEnergy integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("portal_url", default="https://portal.openenergy.example"): str,
    }
)


class OpenEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenEnergy."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step.

        For step 1, we only store a portal URL and create the config entry.
        OAuth and Supervisor actions come in later steps.
        """
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        await self.async_set_unique_id(f"openenergy::{user_input['portal_url']}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="OpenEnergy",
            data={
                "portal_url": user_input["portal_url"].rstrip("/"),
            },
        )


async def async_get_config_entry_data(hass: HomeAssistant, entry_id: str) -> dict:
    """Return config entry data for debugging."""
    entry = hass.config_entries.async_get_entry(entry_id)
    return {} if entry is None else dict(entry.data)

