"""Base entity for Vidaa TV."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_MAC,
    CONF_MODEL,
    CONF_NAME,
    CONF_SW_VERSION,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import VidaaTVDataUpdateCoordinator

if TYPE_CHECKING:
    from . import VidaaTVConfigEntry


class VidaaTVEntity(CoordinatorEntity[VidaaTVDataUpdateCoordinator]):
    """Base class for all Vidaa TV entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the entity."""
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
