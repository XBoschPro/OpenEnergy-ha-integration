"""
Sensors:
- OpenEnergy server health (portal /api/health)
- FRP add-on status (Supervisor add-on info)
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .portal_api import PortalClient, PortalConfig
from .supervisor_api import SupervisorClient, SupervisorApiError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensors from a config entry."""
    portal_url = entry.data["portal_url"]
    portal = PortalClient(hass, PortalConfig(portal_url=portal_url))

    addon_name_contains = entry.data.get("addon_name_contains", "OpenEnergy FRP Client")

    async_add_entities(
        [
            OpenEnergyServerHealthSensor(hass, entry, portal),
            OpenEnergyFrpAddonStatusSensor(hass, entry, addon_name_contains),
        ]
    )


class OpenEnergyServerHealthSensor(SensorEntity):
    """Portal health sensor."""

    _attr_has_entity_name = True
    _attr_name = "OpenEnergy Server Status"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, portal: PortalClient) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._entry = entry
        self._portal = portal
        self._attr_unique_id = f"{entry.entry_id}_server_health"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Update sensor state."""
        try:
            data = await self._portal.async_health()
            self._attr_native_value = "ok" if data.get("ok") else "error"
            self._attr_extra_state_attributes = data
        except Exception as e:
            self._attr_native_value = "error"
            self._attr_extra_state_attributes = {"error": str(e)}


class OpenEnergyFrpAddonStatusSensor(SensorEntity):
    """FRP add-on status sensor."""

    _attr_has_entity_name = True
    _attr_name = "OpenEnergy FRP Client Status"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, addon_name_contains: str) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._entry = entry
        self._addon_name_contains = addon_name_contains
        self._attr_unique_id = f"{entry.entry_id}_frp_addon_status"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Update add-on status."""
        try:
            sup = SupervisorClient(self._hass)
            slug = await sup.async_find_addon_slug(name_contains=self._addon_name_contains)
            info = await sup.async_get_addon_info(slug)
            state = ((info.get("data") or {}).get("state")) or "unknown"
            self._attr_native_value = state
            self._attr_extra_state_attributes = {"addon_slug": slug, "info": info.get("data")}
        except Exception as e:
            self._attr_native_value = "error"
            self._attr_extra_state_attributes = {"error": str(e)}
