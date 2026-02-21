"""Button platform for Vidaa TV."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
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
    BUTTON_KEYS,
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
    """Set up Vidaa TV buttons from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        VidaaTVButton(coordinator, entry, key_id, name, icon, vidaa_key, enabled)
        for key_id, name, icon, vidaa_key, enabled in BUTTON_KEYS
    )


class VidaaTVButton(CoordinatorEntity[VidaaTVDataUpdateCoordinator], ButtonEntity):
    """Representation of a Vidaa TV remote button."""

    _attr_has_entity_name = True

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
        super().__init__(coordinator)
        self._entry = entry
        self._vidaa_key = vidaa_key
        self._mac = entry.data.get(CONF_MAC)
        self._device_id = entry.data.get(CONF_DEVICE_ID) or self._mac
        self._attr_unique_id = f"{self._device_id}_button_{key_id}" if self._device_id else f"{entry.entry_id}_button_{key_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = enabled_default

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
    def available(self) -> bool:
        """Always available so buttons work for WoL scenarios."""
        return True

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.async_send_key(self._vidaa_key)
