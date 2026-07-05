"""The Vidaa TV integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    LOVELACE_DATA,
    MODE_STORAGE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import target as target_helpers
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

REMOTE_CARD_PATH = "/vidaa_tv/vidaa-tv-remote-card.js"
REMOTE_CARD_RESOURCE_URL = f"{REMOTE_CARD_PATH}?v=9"


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
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                REMOTE_CARD_PATH,
                str(Path(__file__).parent / "www" / "vidaa-tv-remote-card.js"),
                False,
            ),
        ]
    )
    await _async_register_lovelace_resource(hass)
    await _async_setup_services(hass)
    return True


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register the bundled remote card as a Lovelace module resource."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace is not loaded; skipping Vidaa TV card resource")
        return

    resource_collection = lovelace_data.resources
    await resource_collection.async_get_info()
    resources = resource_collection.async_items() or []
    matching_resources = [
        item
        for item in resources
        if item.get(CONF_URL, "").startswith(REMOTE_CARD_PATH)
    ]

    if matching_resources and lovelace_data.resource_mode != MODE_STORAGE:
        if not any(item.get(CONF_URL) == REMOTE_CARD_RESOURCE_URL for item in matching_resources):
            _LOGGER.info(
                "Vidaa TV remote card is available at %s. Update the "
                "Lovelace resource manually because Lovelace resources are "
                "in YAML mode.",
                REMOTE_CARD_RESOURCE_URL,
            )
        return

    if lovelace_data.resource_mode != MODE_STORAGE:
        _LOGGER.info(
            "Vidaa TV remote card is available at %s. Add it to Lovelace "
            "resources manually because Lovelace resources are in YAML mode.",
            REMOTE_CARD_RESOURCE_URL,
        )
        return

    if matching_resources:
        current_resource = matching_resources[0]
        if current_resource.get(CONF_URL) != REMOTE_CARD_RESOURCE_URL:
            await resource_collection.async_update_item(
                current_resource[CONF_ID],
                {
                    CONF_RESOURCE_TYPE_WS: "module",
                    CONF_URL: REMOTE_CARD_RESOURCE_URL,
                },
            )
            _LOGGER.info("Updated Vidaa TV remote card Lovelace resource")

        for duplicate_resource in matching_resources[1:]:
            await resource_collection.async_delete_item(duplicate_resource[CONF_ID])
            _LOGGER.info("Removed duplicate Vidaa TV remote card Lovelace resource")
        return

    await resource_collection.async_create_item(
        {
            CONF_RESOURCE_TYPE_WS: "module",
            CONF_URL: REMOTE_CARD_RESOURCE_URL,
        }
    )
    _LOGGER.info("Registered Vidaa TV remote card Lovelace resource")


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

    def _get_targeted_config_entry_ids(call: ServiceCall) -> set[str]:
        """Return config entry IDs referenced by a service target."""
        target_selection = target_helpers.TargetSelection(call.data)
        referenced = target_helpers.async_extract_referenced_entity_ids(
            hass,
            target_selection,
            True,
        )

        config_entry_ids: set[str] = set()
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        for device_id in referenced.referenced_devices:
            device = device_registry.async_get(device_id)
            if device:
                config_entry_ids.update(device.config_entries)

        entity_ids = referenced.referenced | referenced.indirectly_referenced
        for entity_id in entity_ids:
            entity_entry = entity_registry.async_get(entity_id)
            if entity_entry and entity_entry.config_entry_id:
                config_entry_ids.add(entity_entry.config_entry_id)

        return config_entry_ids

    def _get_coordinators(call: ServiceCall) -> list[VidaaTVDataUpdateCoordinator]:
        """Get coordinators targeted by a service call."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_tvs_configured",
            )

        targeted_config_entry_ids = _get_targeted_config_entry_ids(call)
        return [
            entry.runtime_data.coordinator
            for entry in entries
            if not entry.state.recoverable
            and (
                not targeted_config_entry_ids
                or entry.entry_id in targeted_config_entry_ids
            )
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
