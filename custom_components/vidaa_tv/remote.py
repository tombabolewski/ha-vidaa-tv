"""Remote platform for Vidaa TV."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Iterable

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
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

from vidaa.keys import get_key, ALL_KEYS

if TYPE_CHECKING:
    from . import VidaaTVConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaTVConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vidaa TV remote from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VidaaTVRemote(coordinator, entry)])


class VidaaTVRemote(CoordinatorEntity[VidaaTVDataUpdateCoordinator], RemoteEntity):
    """Representation of a Vidaa TV remote."""

    _attr_has_entity_name = True
    _attr_name = "Remote"
    _attr_supported_features = RemoteEntityFeature.ACTIVITY

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the remote."""
        super().__init__(coordinator)
        self._entry = entry
        self._mac = entry.data.get(CONF_MAC)
        self._device_id = entry.data.get(CONF_DEVICE_ID) or self._mac
        self._attr_unique_id = f"{self._device_id}_remote" if self._device_id else f"{entry.entry_id}_remote"
        self._apps: list[dict] = []
        self._activity_list: list[str] = []

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        await self._async_update_activities()

    async def _async_update_activities(self) -> None:
        """Update activity list from TV."""
        try:
            apps = await self.coordinator.async_get_apps()
            if apps:
                self._apps = apps
                self._activity_list = [app.get("name") for app in apps if app.get("name")]
        except Exception as err:
            _LOGGER.debug("Error updating activities: %s", err)

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
        """Return if entity is available."""
        return self.coordinator.available

    @property
    def is_on(self) -> bool | None:
        """Return if TV is on."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("is_on", False)

    @property
    def current_activity(self) -> str | None:
        """Return current activity (app name or source)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("app") or self.coordinator.data.get("source")

    @property
    def activity_list(self) -> list[str] | None:
        """Return list of activities (apps)."""
        return self._activity_list if self._activity_list else None

    async def async_turn_on(self, activity: str | None = None, **kwargs: Any) -> None:
        """Turn the TV on and optionally start an activity."""
        await self.coordinator.async_turn_on()
        if activity:
            await self.coordinator.async_launch_app(activity)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the TV off."""
        await self.coordinator.async_turn_off()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send remote commands."""
        num_repeats = kwargs.get("num_repeats", 1)
        delay_secs = kwargs.get("delay_secs", 0.2)

        for _ in range(num_repeats):
            for cmd in command:
                key = get_key(cmd)
                await self.coordinator.async_send_key(key)

                if delay_secs > 0:
                    import asyncio
                    await asyncio.sleep(delay_secs)

    async def async_learn_command(self, **kwargs: Any) -> None:
        """Learn a command (not supported)."""
        _LOGGER.warning("Learning commands is not supported on Vidaa TV")

    async def async_delete_command(self, **kwargs: Any) -> None:
        """Delete a command (not supported)."""
        _LOGGER.warning("Deleting commands is not supported on Vidaa TV")
