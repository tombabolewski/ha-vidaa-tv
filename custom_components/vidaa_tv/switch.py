"""Switch platform for Vidaa TV."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
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

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaTVConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vidaa TV switches from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VidaaTVMuteSwitch(coordinator, entry)])


class VidaaTVMuteSwitch(CoordinatorEntity[VidaaTVDataUpdateCoordinator], SwitchEntity):
    """Switch to toggle mute on the TV."""

    _attr_has_entity_name = True
    _attr_name = "Mute"
    _attr_icon = "mdi:volume-off"

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the mute switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._mac = entry.data.get(CONF_MAC)
        self._device_id = entry.data.get(CONF_DEVICE_ID) or self._mac
        self._attr_unique_id = f"{self._device_id}_switch_mute" if self._device_id else f"{entry.entry_id}_switch_mute"

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

    @property
    def is_on(self) -> bool | None:
        """Return True if muted."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("is_muted", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the TV."""
        if not self.is_on:
            await self.coordinator.async_mute()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the TV."""
        if self.is_on:
            await self.coordinator.async_mute()
