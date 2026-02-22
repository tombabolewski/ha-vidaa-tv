"""The Vidaa TV integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_MAC,
    DEFAULT_PORT,
    PLATFORMS,
    SERVICE_SEND_KEY,
    SERVICE_LAUNCH_APP,
    ATTR_KEY,
    ATTR_APP,
)
from .coordinator import VidaaTVDataUpdateCoordinator

from vidaa.keys import ALL_KEYS

_LOGGER = logging.getLogger(__name__)

from vidaa import AsyncVidaaTV
from vidaa.config import TokenStorage


@dataclass
class VidaaTVRuntimeData:
    """Runtime data for Vidaa TV integration."""

    coordinator: VidaaTVDataUpdateCoordinator
    tv: AsyncVidaaTV


# Python 3.11 compatible type alias (not 3.12+ type statement)
VidaaTVConfigEntry = ConfigEntry[VidaaTVRuntimeData]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Vidaa TV integration."""
    await _async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VidaaTVConfigEntry) -> bool:
    """Set up Vidaa TV from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    mac = entry.data.get(CONF_MAC)

    _LOGGER.debug("Setting up Vidaa TV at %s:%s", host, port)

    # Set up token storage in HA config directory
    config_dir = Path(hass.config.config_dir)
    storage = TokenStorage(config_dir / ".vidaa_tv_tokens.json")

    # Create the async TV client (certs are bundled in vidaa-control library)
    tv = AsyncVidaaTV(
        host=host,
        port=port,
        mac_address=mac,
        use_dynamic_auth=True,
        enable_persistence=True,
        storage=storage,
    )

    # Try to connect
    try:
        connected = await tv.async_connect(timeout=10)
        if not connected:
            raise ConfigEntryNotReady("Failed to connect to TV")
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.debug("Error connecting to TV: %s", err)
        raise ConfigEntryNotReady("Error connecting to TV") from err

    # Create coordinator for data updates
    coordinator = VidaaTVDataUpdateCoordinator(hass, tv, entry)
    await coordinator.async_config_entry_first_refresh()

    # Store runtime data
    entry.runtime_data = VidaaTVRuntimeData(coordinator=coordinator, tv=tv)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the integration."""

    def _get_coordinators(call: ServiceCall) -> list[VidaaTVDataUpdateCoordinator]:
        """Get coordinators targeted by a service call."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_tvs_configured",
            )

        return [
            entry.runtime_data.coordinator
            for entry in entries
            if not entry.state.recoverable
        ]

    async def async_send_key(call: ServiceCall) -> None:
        """Handle send_key service call."""
        key = call.data[ATTR_KEY]
        # Validate key against known keys
        if key not in ALL_KEYS:
            raise ServiceValidationError(
                f"Unknown key '{key}'. Must be one of: {', '.join(sorted(ALL_KEYS))}",
            )
        for coordinator in _get_coordinators(call):
            try:
                await coordinator.async_send_key(key)
            except Exception as err:
                _LOGGER.error("send_key failed: %s", err)
                raise HomeAssistantError("Failed to send key to TV") from err

    async def async_launch_app(call: ServiceCall) -> None:
        """Handle launch_app service call."""
        app = call.data[ATTR_APP]
        for coordinator in _get_coordinators(call):
            try:
                await coordinator.async_launch_app(app)
            except Exception as err:
                _LOGGER.error("launch_app failed: %s", err)
                raise HomeAssistantError("Failed to launch app on TV") from err

    # Only register services once
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_KEY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_KEY,
            async_send_key,
            schema=vol.Schema({
                vol.Required(ATTR_KEY): cv.string,
            }),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_LAUNCH_APP):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LAUNCH_APP,
            async_launch_app,
            schema=vol.Schema({
                vol.Required(ATTR_APP): cv.string,
            }),
        )


async def async_unload_entry(hass: HomeAssistant, entry: VidaaTVConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        runtime_data = entry.runtime_data
        if runtime_data.tv:
            await runtime_data.tv.async_disconnect()

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: VidaaTVConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
