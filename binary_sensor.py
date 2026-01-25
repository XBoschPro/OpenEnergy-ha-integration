"""Binary sensor for OpenEnergy."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OpenEnergyCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenEnergy binary sensors."""
    coordinator: OpenEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([OpenEnergyConnectivitySensor(coordinator)])


class OpenEnergyConnectivitySensor(CoordinatorEntity[OpenEnergyCoordinator], BinarySensorEntity):
    """Binary sensor representing connection status to OpenEnergy Cloud."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenEnergyCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_connectivity"
        self._attr_name = "Cloud Connection"

    @property
    def is_on(self) -> bool:
        """Return true if connected."""
        # Connected if health check passed AND we have a token
        return (
            self.coordinator.data.get("health_ok", False)
            and self.coordinator.data.get("has_token", False)
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Return details about the connection."""
        return {
            "health_details": self.coordinator.data.get("health_details"),
            "token_provisioned": self.coordinator.data.get("has_token", False),
        }
