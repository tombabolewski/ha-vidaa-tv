"""Sensor platform for Vidaa TV."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_MAC,
    CONF_DEVICE_ID,
    CONF_MODEL,
    CONF_SW_VERSION,
    DEFAULT_NAME,
)
from .coordinator import VidaaTVDataUpdateCoordinator

if TYPE_CHECKING:
    from . import VidaaTVConfigEntry

_LOGGER = logging.getLogger(__name__)


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


class VidaaTVSensorBase(CoordinatorEntity[VidaaTVDataUpdateCoordinator], SensorEntity):
    """Base class for Vidaa TV sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._mac = entry.data.get(CONF_MAC)
        self._device_id = entry.data.get(CONF_DEVICE_ID) or self._mac

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device_id = self._entry.data.get(CONF_DEVICE_ID) or self._mac
        mac = self._entry.data.get(CONF_MAC)

        info = DeviceInfo(
            identifiers={(DOMAIN, device_id or self._entry.entry_id)},
            name=self._entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Hisense",
            model=self._entry.data.get(CONF_MODEL),
            sw_version=self._entry.data.get(CONF_SW_VERSION),
        )

        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac.lower())}

        return info


class VidaaTVAppSensor(VidaaTVSensorBase):
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


class VidaaTVSourceSensor(VidaaTVSensorBase):
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
