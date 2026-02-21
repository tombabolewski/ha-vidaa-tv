"""Media Player platform for Vidaa TV."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
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
    """Set up Vidaa TV media player from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VidaaTVMediaPlayer(coordinator, entry)])


class VidaaTVMediaPlayer(CoordinatorEntity[VidaaTVDataUpdateCoordinator], MediaPlayerEntity):
    """Representation of a Vidaa TV media player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_has_entity_name = True
    _attr_name = None  # Use device name

    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PLAY_MEDIA
    )

    def __init__(
        self,
        coordinator: VidaaTVDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._entry = entry
        self._mac = entry.data.get(CONF_MAC)
        self._device_id = entry.data.get(CONF_DEVICE_ID) or self._mac
        self._attr_unique_id = f"{self._device_id}_media_player" if self._device_id else entry.entry_id

        # Source and app caches
        self._sources: list[str] = []
        self._apps: list[dict] = []
        self._source_list: list[str] = []

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
        """Return if entity is available.

        Always available so power button works for WoL even when TV is off.
        """
        return True

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the TV."""
        if not self.coordinator.data or not self.coordinator.available:
            return MediaPlayerState.OFF

        if self.coordinator.data.get("is_on"):
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Return volume level (0.0 to 1.0)."""
        if not self.coordinator.data:
            return None

        volume = self.coordinator.data.get("volume")
        if volume is not None:
            return volume / 100.0
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return if volume is muted."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("is_muted", False)

    @property
    def source(self) -> str | None:
        """Return current source."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("source")

    @property
    def source_list(self) -> list[str]:
        """Return list of available sources."""
        return self._source_list

    @property
    def app_name(self) -> str | None:
        """Return current app name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("app")

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        await self._async_update_sources()

    async def _async_update_sources(self) -> None:
        """Update source list from TV."""
        try:
            sources = await self.coordinator.async_get_sources()
            if sources and isinstance(sources, list):
                self._sources = sources
                self._source_list = []
                for s in sources:
                    if isinstance(s, dict):
                        name = s.get("sourcename", s.get("name", f"Source {s.get('sourceid', '?')}"))
                        self._source_list.append(name)

            apps = await self.coordinator.async_get_apps()
            if apps and isinstance(apps, list):
                self._apps = apps
                for app in apps:
                    if isinstance(app, dict):
                        name = app.get("name")
                        if name and name not in self._source_list:
                            self._source_list.append(name)

        except Exception as err:
            _LOGGER.debug("Error updating sources: %s", err)

    async def async_turn_on(self) -> None:
        """Turn the TV on."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        """Turn the TV off."""
        await self.coordinator.async_turn_off()

    async def async_volume_up(self) -> None:
        """Increase volume."""
        await self.coordinator.async_volume_up()

    async def async_volume_down(self) -> None:
        """Decrease volume."""
        await self.coordinator.async_volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self.coordinator.async_mute()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0.0 to 1.0)."""
        await self.coordinator.async_set_volume(int(volume * 100))

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        for app in self._apps:
            if app.get("name") == source:
                await self.coordinator.async_launch_app(source)
                return

        await self.coordinator.async_select_source(source)

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.async_send_key("KEY_PLAY")

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.async_send_key("KEY_PAUSE")

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self.coordinator.async_send_key("KEY_STOP")

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self.coordinator.async_send_key("KEY_FAST_FORWARD")

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self.coordinator.async_send_key("KEY_REWIND")

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media - used for launching apps."""
        if media_type == "app":
            await self.coordinator.async_launch_app(media_id)
