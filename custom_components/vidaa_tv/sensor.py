"""Sensor platform for Vidaa TV."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VidaaTVDataUpdateCoordinator
from .entity import VidaaTVEntity

if TYPE_CHECKING:
    from . import VidaaTVConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaTVConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vidaa TV sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([
        VidaaTVAppSensor(coordinator, entry),
        VidaaTVSourceSensor(coordinator, entry),
    ])


class VidaaTVAppSensor(VidaaTVEntity, SensorEntity):
    """Sensor showing the current app."""

    _attr_name = "Current App"
    _attr_icon = "mdi:apps"

    def __init__(self, coordinator: VidaaTVDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the app sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_sensor_app" if self._device_id else f"{entry.entry_id}_sensor_app"

    @property
    def native_value(self) -> str | None:
        """Return current app name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("app")


class VidaaTVSourceSensor(VidaaTVEntity, SensorEntity):
    """Sensor showing the current source/input."""

    _attr_name = "Current Source"
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator: VidaaTVDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the source sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_sensor_source" if self._device_id else f"{entry.entry_id}_sensor_source"

    @property
    def native_value(self) -> str | None:
        """Return current source name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("source")
