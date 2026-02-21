"""Diagnostics support for Vidaa TV."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import VidaaTVConfigEntry

TO_REDACT = {
    "mac",
    "device_id",
    "host",
    "network_type",
    "eth0",
    "wlan0",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VidaaTVConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    tv = runtime_data.tv

    device_info = None
    if tv and tv.is_connected:
        try:
            device_info = await tv.async_get_device_info(timeout=5)
        except Exception:
            pass

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "data": coordinator.data,
            "available": coordinator.available,
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
        "tv_connection": {
            "connected": tv.is_connected if tv else False,
            "device_info": async_redact_data(device_info, TO_REDACT) if device_info else None,
        },
    }
