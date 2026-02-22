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

    _LOGGER.debug("Setting up Vidaa TV at %s:%s (mac=%s)", host, port, mac)

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
            raise ConfigEntryNotReady(f"Failed to connect to TV at {host}")
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Error connecting to TV: %s", err)
        raise ConfigEntryNotReady(f"Error connecting to TV: {err}") from err

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

    async def _async_call_all_tvs(action) -> None:
        """Run an async action on all loaded TV coordinators."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_tvs_configured",
            )

        for entry in entries:
            if entry.state.recoverable:
                continue
            runtime_data: VidaaTVRuntimeData = entry.runtime_data
            try:
                await action(runtime_data.coordinator)
            except Exception as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(err)},
                ) from err

    async def async_send_key(call: ServiceCall) -> None:
        """Handle send_key service call."""
        key = call.data[ATTR_KEY]
        await _async_call_all_tvs(lambda c: c.async_send_key(key))

    async def async_launch_app(call: ServiceCall) -> None:
        """Handle launch_app service call."""
        app = call.data[ATTR_APP]
        await _async_call_all_tvs(lambda c: c.async_launch_app(app))

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
