"""Data update coordinator for Vidaa TV."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from vidaa import APPS
from vidaa.wol import wake_tv
from .const import DOMAIN, SCAN_INTERVAL, STATE_FAKE_SLEEP, CONF_MAC, CONF_HOST, CONF_DEVICE_ID

_LOGGER = logging.getLogger(__name__)


class VidaaTVDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates from Vidaa TV."""

    def __init__(
        self,
        hass: HomeAssistant,
        tv,  # AsyncVidaaTV
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = entry.options.get("scan_interval", SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.tv = tv
        self.entry = entry
        self._available = True
        self._device_info_fetched = False
        self._auth_failures = 0

    @property
    def available(self) -> bool:
        """Return if TV is available."""
        return self._available

    async def _async_update_device_info(self) -> None:
        """Fetch and update device info in the device registry."""
        if self._device_info_fetched:
            return

        try:
            device_info = await self.tv.async_get_device_info(timeout=5)
            _LOGGER.debug("Got device info: %s", device_info)

            if not device_info:
                return

            # Use MAC from config entry as primary identifier
            mac = self.entry.data.get(CONF_MAC)
            device_id = self.entry.data.get(CONF_DEVICE_ID) or mac

            if not device_id:
                # Fallback: extract from device_info
                network_type = device_info.get("network_type", "")
                device_id = device_info.get(f"{network_type}0") or device_info.get("wlan0") or device_info.get("eth0")

            # Update device registry
            device_registry = dr.async_get(self.hass)
            device_entry = None

            if device_id:
                device_entry = device_registry.async_get_device(
                    identifiers={(DOMAIN, device_id)}
                )

            if not device_entry:
                device_entry = device_registry.async_get_device(
                    identifiers={(DOMAIN, self.entry.entry_id)}
                )

            if device_entry:
                updates = {}
                model = device_info.get("model_name")
                sw_version = device_info.get("tv_version")
                name = device_info.get("tv_name")

                if model and model != device_entry.model:
                    updates["model"] = model
                if sw_version and sw_version != device_entry.sw_version:
                    updates["sw_version"] = sw_version
                if name and name != device_entry.name:
                    updates["name"] = name

                if updates:
                    device_registry.async_update_device(device_entry.id, **updates)
                    device_registry.async_schedule_save()

                    new_data = dict(self.entry.data)
                    if model:
                        new_data["model"] = model
                    if sw_version:
                        new_data["sw_version"] = sw_version
                    if device_id:
                        new_data["device_id"] = device_id
                    self.hass.config_entries.async_update_entry(self.entry, data=new_data)

            self._device_info_fetched = True

        except Exception as err:
            _LOGGER.warning("Error fetching device info: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from TV."""
        import time
        start = time.monotonic()

        try:
            if not self.tv.is_connected:
                _LOGGER.debug("TV disconnected, attempting reconnect")
                try:
                    await self.tv.async_disconnect()
                except Exception:
                    pass
                connected = await self.tv.async_connect(timeout=5)
                if not connected:
                    self._available = False
                    raise UpdateFailed("Failed to connect to TV")

            self._available = True

            # Update device info on first successful connection
            await self._async_update_device_info()

            # Get current state
            state = await self.tv.async_get_state(timeout=3)

            # Determine power state
            is_on = True
            if state:
                if state.get("statetype") == STATE_FAKE_SLEEP:
                    is_on = False
            else:
                is_on = False

            # Get volume (only if TV is on)
            volume = None
            is_muted = False
            if is_on:
                try:
                    volume = await self.tv.async_get_volume(timeout=1)
                    is_muted = self.tv.is_muted
                except Exception as err:
                    _LOGGER.debug("get_volume failed: %s", err)

            # Extract current app or source
            statetype = state.get("statetype") if state else None
            app = None
            source = None
            if state:
                if statetype == "app":
                    app_key = state.get("name", "").lower()
                    if app_key in APPS:
                        app = APPS[app_key].get("name", app_key)
                    else:
                        app = state.get("name", "").capitalize()
                elif statetype == "sourceswitch":
                    source = state.get("displayname") or state.get("sourcename")

            data = {
                "is_on": is_on,
                "state": state,
                "statetype": statetype,
                "volume": volume,
                "is_muted": is_muted,
                "app": app,
                "source": source,
            }

            _LOGGER.debug("State: on=%s, type=%s, vol=%s, app=%s, src=%s (%.2fs)",
                         is_on, statetype, volume, app, source, time.monotonic() - start)
            return data

        except Exception as err:
            self._available = False
            error_str = str(err).lower()
            if "auth" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
                self._auth_failures += 1
                if self._auth_failures >= 3:
                    raise ConfigEntryAuthFailed(
                        "Authentication failed. Please re-pair with the TV."
                    ) from err
            raise UpdateFailed(f"Error communicating with TV: {err}") from err

    async def async_turn_on(self) -> None:
        """Turn TV on using WoL and power command."""
        # Use MAC directly from config entry
        mac = self.entry.data.get(CONF_MAC)
        if mac:
            host = self.entry.data.get(CONF_HOST, "")
            subnet = host.rsplit(".", 1)[0] if "." in host else None
            _LOGGER.debug("Sending WoL to %s", mac)
            await self.hass.async_add_executor_job(wake_tv, mac, subnet)

        await self.tv.async_power_on()
        await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn TV off."""
        await self.tv.async_power_off()
        await self.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Increase volume."""
        await self.tv.async_volume_up()
        await self.async_request_refresh()

    async def async_volume_down(self) -> None:
        """Decrease volume."""
        await self.tv.async_volume_down()
        await self.async_request_refresh()

    async def async_mute(self) -> None:
        """Toggle mute."""
        await self.tv.async_mute()
        await self.async_request_refresh()

    async def async_set_volume(self, volume: int) -> None:
        """Set volume level."""
        await self.tv.async_set_volume(volume)
        await self.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        await self.tv.async_set_source(source)
        await self.async_request_refresh()

    async def async_send_key(self, key: str) -> None:
        """Send remote key."""
        await self.tv.async_send_key(key)

    async def async_launch_app(self, app_name: str) -> None:
        """Launch app."""
        await self.tv.async_launch_app(app_name)
        await self.async_request_refresh()

    async def async_get_apps(self) -> list[dict] | None:
        """Get available apps."""
        return await self.tv.async_get_apps()

    async def async_get_sources(self) -> list[dict] | None:
        """Get available sources."""
        return await self.tv.async_get_sources()
