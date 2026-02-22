"""Switch platform for Vidaa TV."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Vidaa TV switches from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VidaaTVMuteSwitch(coordinator, entry)])


class VidaaTVMuteSwitch(VidaaTVEntity, SwitchEntity):
    """Switch to toggle mute on the TV."""

    _attr_name = "Mute"
    _attr_icon = "mdi:volume-off"

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the mute switch."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_id}_switch_mute" if self._device_id else f"{entry.entry_id}_switch_mute"

    @property
    def is_on(self) -> bool | None:
        """Return True if muted."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("is_muted", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the TV."""
        if self.is_on is not True:
            await self.coordinator.async_mute()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the TV."""
        if self.is_on is True:
            await self.coordinator.async_mute()
