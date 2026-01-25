"""Sensor for OpenEnergy."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
    """Set up OpenEnergy sensors."""
    coordinator: OpenEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([OpenEnergyLatencySensor(coordinator)])


class OpenEnergyLatencySensor(CoordinatorEntity[OpenEnergyCoordinator], SensorEntity):
    """Sensor representing latency to OpenEnergy Cloud."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenEnergyCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_latency"
        self._attr_name = "API Latency"

    @property
    def native_value(self) -> float | None:
        """Return the latency in ms."""
        if not self.coordinator.data.get("health_ok"):
            return None
        return self.coordinator.data.get("latency_ms")
