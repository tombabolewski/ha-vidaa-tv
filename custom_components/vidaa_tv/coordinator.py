"""Data update coordinator for Vidaa TV."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from vidaa import APPS, AsyncVidaaTV
from vidaa.config import TokenStorage
from vidaa.wol import wake_tv
from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    STATE_FAKE_SLEEP,
    CONF_MAC,
    CONF_HOST,
    CONF_PORT,
    CONF_DEVICE_ID,
    DEFAULT_PORT,
    TOKEN_FILE,
    TOKEN_REFRESH_BEFORE,
    TOKEN_CHECK_INTERVAL,
    AUTH_FAILURES_BEFORE_REAUTH,
)

_LOGGER = logging.getLogger(__name__)


def get_token_storage(hass: HomeAssistant) -> TokenStorage:
    """Get token storage in HA config directory."""
    return TokenStorage(Path(hass.config.config_dir) / TOKEN_FILE)


def create_tv_client(
    hass: HomeAssistant, host: str, port: int, mac: str | None
) -> AsyncVidaaTV:
    """Create an AsyncVidaaTV client (certs are bundled in vidaa-control)."""
    return AsyncVidaaTV(
        host=host,
        port=port,
        mac_address=mac,
        use_dynamic_auth=True,
        enable_persistence=True,
        storage=get_token_storage(hass),
    )


def clear_saved_token(
    storage: TokenStorage,
    host: str,
    port: int,
    mac: str | None,
    only_expired: bool = False,
) -> None:
    """Remove the cached tokens of a TV so the next connection pairs again.

    A TV paired by hostname may be cached under its host and later under its
    MAC, so keep deleting until no token is found. Blocking (file I/O).
    """
    for _ in range(3):
        status = storage.get_token_status(device_id=mac, host=host, port=port)
        if not status["has_token"] or (only_expired and status["access_valid"]):
            return
        storage.delete_token(device_id=mac, host=host, port=port)


async def async_is_reachable(host: str, port: int, timeout: float = 3) -> bool:
    """Check whether the TV accepts TCP connections on its MQTT port."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    with suppress(Exception):
        await writer.wait_closed()
    return True


class VidaaTVDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates from Vidaa TV."""

    def __init__(
        self,
        hass: HomeAssistant,
        tv: AsyncVidaaTV,
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
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
        self._storage = get_token_storage(hass)
        self._available = True
        self._device_info_fetched = False
        self._auth_failures = 0
        self._last_token_check: float | None = None

    @property
    def available(self) -> bool:
        """Return if TV is available."""
        return self._available

    async def _async_reconnect(self) -> None:
        """Reconnect to the TV with a new client.

        vidaa-control only reads the token cache when a client is created, so
        reusing the old client keeps sending an expired access token as the
        MQTT password. A new client picks up refreshed tokens and connects with
        the refresh token when the access token expired.
        """
        with suppress(Exception):
            await self.tv.async_disconnect()

        self.tv = create_tv_client(
            self.hass, self._host, self._port, self.entry.data.get(CONF_MAC)
        )
        if await self.tv.async_connect(timeout=5):
            self._auth_failures = 0
            return

        self._available = False
        if await async_is_reachable(self._host, self._port):
            # TV is up but refused the session: the saved credentials are bad
            self._auth_failures += 1
            if self._auth_failures >= AUTH_FAILURES_BEFORE_REAUTH:
                raise ConfigEntryAuthFailed(
                    "The TV rejected the saved credentials. Please re-pair with the TV."
                )
        raise UpdateFailed("Failed to connect to TV")

    async def _async_ensure_token_fresh(self) -> None:
        """Refresh the access token before it expires.

        The TV can only refresh tokens while it is reachable, so refresh while
        connected instead of waiting for the access token to expire.
        """
        now = time.monotonic()
        if self._last_token_check is not None and now - self._last_token_check < TOKEN_CHECK_INTERVAL:
            return
        self._last_token_check = now

        status = await self.hass.async_add_executor_job(
            partial(
                self._storage.get_token_status,
                device_id=self.entry.data.get(CONF_MAC),
                host=self._host,
                port=self._port,
            )
        )
        if not status["has_token"] or not status["refresh_valid"]:
            return
        if status["access_valid"] and status["access_expires_in"] > TOKEN_REFRESH_BEFORE:
            return

        _LOGGER.debug("Access token expires in %ss, refreshing", status["access_expires_in"])
        if not await self.tv.async_refresh_token(timeout=10):
            _LOGGER.warning("Could not refresh the TV access token")
            return

        # Start a new session so the refreshed tokens are used from now on
        await self._async_reconnect()

    async def _async_update_device_info(self) -> None:
        """Fetch and update device info in the device registry."""
        if self._device_info_fetched:
            return

        try:
            device_info = await self.tv.async_get_device_info(timeout=5)
            _LOGGER.debug("Got device info for %s", self.entry.data.get(CONF_HOST))

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
        start = time.monotonic()

        try:
            if not self.tv.is_connected:
                _LOGGER.debug("TV disconnected, attempting reconnect")
                await self._async_reconnect()

            self._available = True

            await self._async_ensure_token_fresh()

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

        except (ConfigEntryAuthFailed, UpdateFailed):
            raise
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
