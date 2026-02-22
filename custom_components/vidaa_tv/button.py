"""Button platform for Vidaa TV."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BUTTON_KEYS
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
    """Set up Vidaa TV buttons from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        VidaaTVButton(coordinator, entry, key_id, name, icon, vidaa_key, enabled)
        for key_id, name, icon, vidaa_key, enabled in BUTTON_KEYS
    )


class VidaaTVButton(VidaaTVEntity, ButtonEntity):
    """Representation of a Vidaa TV remote button."""

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
        key_id: str,
        name: str,
        icon: str,
        vidaa_key: str,
        enabled_default: bool,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, entry)
        self._vidaa_key = vidaa_key
        self._attr_unique_id = f"{self._device_id}_button_{key_id}" if self._device_id else f"{entry.entry_id}_button_{key_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def available(self) -> bool:
        """Always available so buttons work for WoL scenarios."""
        return True

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.async_send_key(self._vidaa_key)
