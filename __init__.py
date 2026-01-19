"""OpenEnergy integration.

Current scope:
- Device Authorization Grant (Keycloak)
- Exchange Keycloak access token -> OpenEnergy opaque token (server-side)
- Options menu (status, reconnect, rotate token, disconnect, advanced info)

Later:
- Supervisor add-on bootstrap
- Patch configuration.yaml
- FRP provisioning
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenEnergy from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "title": entry.title,
        "data": dict(entry.data),
        "options": dict(entry.options),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenEnergy config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
