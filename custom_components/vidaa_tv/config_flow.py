"""Config flow for Vidaa TV integration."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_DEVICE_ID,
    CONF_MAC,
    CONF_MODEL,
    CONF_SW_VERSION,
    DEFAULT_NAME,
    DEFAULT_PORT,
    TIMEOUT_CONNECT,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

from vidaa import AsyncVidaaTV
from vidaa.config import TokenStorage
from vidaa.wol import get_mac_from_ip


def _extract_mac_from_device_info(device_info: dict) -> str | None:
    """Extract real MAC address from device_info.

    The TV reports network_type as 'wlan' or 'eth', and the actual MAC
    is stored under the interface name (e.g. 'wlan0', 'eth0').
    """
    if not device_info:
        return None

    network_type = device_info.get("network_type", "")
    # Try the specific interface first (e.g. wlan0, eth0)
    mac = device_info.get(f"{network_type}0")
    if not mac:
        # Fallback: try both
        mac = device_info.get("wlan0") or device_info.get("eth0")

    if mac and re.match(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", mac):
        return mac.upper().replace("-", ":")

    return None


class VidaaTVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vidaa TV."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str = DEFAULT_NAME
        self._mac: str | None = None
        self._device_id: str | None = None
        self._model: str | None = None
        self._sw_version: str | None = None
        self._discovery_info: ssdp.SsdpServiceInfo | None = None
        # Keep single client alive across steps for pairing
        self._tv: AsyncVidaaTV | None = None

    async def _async_cleanup_client(self) -> None:
        """Disconnect and clean up any active client."""
        if self._tv:
            try:
                await self._tv.async_disconnect()
            except Exception:
                pass
            self._tv = None

    async def _async_resolve_mac(self) -> str | None:
        """Resolve MAC address from IP via ARP."""
        if not self._host:
            return None
        try:
            loop = asyncio.get_running_loop()
            mac = await loop.run_in_executor(None, get_mac_from_ip, self._host)
            if mac:
                return mac.upper().replace("-", ":")
        except Exception as err:
            _LOGGER.debug("Could not resolve MAC from ARP: %s", err)
        return None

    def _get_storage(self) -> TokenStorage:
        """Get token storage in HA config directory."""
        config_dir = Path(self.hass.config.config_dir)
        return TokenStorage(config_dir / ".vidaa_tv_tokens.json")

    async def _async_create_client(self) -> AsyncVidaaTV:
        """Create an AsyncVidaaTV client with current settings.

        Certs are bundled in the vidaa-control library, no need to specify paths.
        """
        return AsyncVidaaTV(
            host=self._host,
            port=self._port,
            use_dynamic_auth=True,
            mac_address=self._mac,
            enable_persistence=True,
            storage=self._get_storage(),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (manual IP entry)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Resolve MAC from ARP
            self._mac = await self._async_resolve_mac()
            _LOGGER.debug("Resolved MAC from ARP: %s", self._mac)

            # Connect and start pairing
            await self._async_cleanup_client()
            self._tv = await self._async_create_client()

            try:
                connected = await self._tv.async_connect(timeout=TIMEOUT_CONNECT)
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    # Get device info to extract real MAC if ARP failed
                    device_info = await self._tv.async_get_device_info(timeout=5)
                    if device_info:
                        self._name = device_info.get("tv_name", DEFAULT_NAME)
                        self._model = device_info.get("model_name")
                        self._sw_version = device_info.get("tv_version")

                        # Extract MAC from device_info if we don't have one
                        info_mac = _extract_mac_from_device_info(device_info)
                        if info_mac:
                            self._mac = info_mac
                            self._device_id = self._mac
                        _LOGGER.debug("Device info MAC: %s", info_mac)

                    # Use MAC as device_id for uniqueness
                    if self._mac:
                        self._device_id = self._mac
                        await self.async_set_unique_id(
                            self._mac.replace(":", "").lower()
                        )
                        self._abort_if_unique_id_configured(
                            updates={CONF_HOST: self._host, CONF_PORT: self._port}
                        )

                    # Start pairing - TV shows PIN
                    await self._tv.async_start_pairing()
                    # Brief pause to let PIN appear on TV
                    await asyncio.sleep(1)

                    return await self.async_step_pair()

            except Exception as err:
                _LOGGER.debug("Config flow connection error: %s: %s", type(err).__name__, err)
                errors["base"] = "unknown"
                await self._async_cleanup_client()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle pairing step (PIN entry).

        The client (self._tv) is kept alive from async_step_user so the
        pairing session on the TV stays active.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            pin = user_input.get("pin", "")

            if not self._tv:
                errors["base"] = "cannot_connect"
            else:
                try:
                    # Authenticate with PIN using the SAME client that started pairing
                    success = await self._tv.async_authenticate(pin, timeout=10)

                    if success:
                        # Get device info to confirm and update details
                        device_info = await self._tv.async_get_device_info(timeout=5)
                        if device_info:
                            self._name = device_info.get("tv_name") or self._name
                            self._model = device_info.get("model_name") or self._model
                            self._sw_version = device_info.get("tv_version") or self._sw_version

                            info_mac = _extract_mac_from_device_info(device_info)
                            if info_mac:
                                self._mac = info_mac
                                self._device_id = self._mac

                        await self._tv.async_disconnect()
                        self._tv = None

                        # Set unique ID
                        if self._device_id:
                            await self.async_set_unique_id(
                                self._device_id.replace(":", "").lower()
                            )
                            self._abort_if_unique_id_configured(
                                updates={CONF_HOST: self._host, CONF_PORT: self._port}
                            )

                        data = {
                            CONF_HOST: self._host,
                            CONF_PORT: self._port,
                            CONF_NAME: self._name,
                            CONF_MAC: self._mac,
                            CONF_DEVICE_ID: self._device_id,
                            CONF_MODEL: self._model,
                            CONF_SW_VERSION: self._sw_version,
                        }

                        # Handle reauth
                        if self.source == config_entries.SOURCE_REAUTH:
                            return self.async_update_reload_and_abort(
                                self._get_reauth_entry(),
                                data=data,
                            )

                        return self.async_create_entry(
                            title=self._name,
                            data=data,
                        )
                    else:
                        errors["base"] = "invalid_pin"
                        # Re-trigger pairing so TV shows PIN again
                        try:
                            await self._tv.async_start_pairing()
                            await asyncio.sleep(1)
                        except Exception:
                            _LOGGER.debug("Could not re-trigger PIN")

                except Exception as err:
                    _LOGGER.exception("Error during pairing: %s", err)
                    errors["base"] = "pairing_failed"

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema(
                {
                    vol.Required("pin"): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "name": self._name,
                "host": self._host or "",
            },
        )

    async def async_step_ssdp(
        self, discovery_info: ssdp.SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle SSDP discovery."""
        _LOGGER.debug("SSDP discovery: %s", discovery_info)

        # Check for vidaa_support=1 in modelDescription
        model_desc = discovery_info.upnp.get("modelDescription", "")
        vidaa_support = False
        for line in model_desc.split("\n"):
            if "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "vidaa_support" and value.strip() == "1":
                    vidaa_support = True
                    break

        if not vidaa_support:
            return self.async_abort(reason="not_vidaa_tv")

        # Extract host
        self._host = discovery_info.ssdp_headers.get("_host") or discovery_info.ssdp_location
        if self._host and "://" in self._host:
            from urllib.parse import urlparse
            parsed = urlparse(self._host)
            self._host = parsed.hostname

        if not self._host:
            return self.async_abort(reason="no_host")

        self._discovery_info = discovery_info
        self._name = discovery_info.upnp.get("friendlyName", DEFAULT_NAME)

        # Set unique ID from USN
        usn = discovery_info.ssdp_usn
        if usn:
            if "::" in usn:
                unique_id = usn.split("::")[0].replace("uuid:", "")
            else:
                unique_id = usn.replace("uuid:", "")
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered device, then proceed to pairing."""
        if user_input is not None:
            # Resolve MAC
            self._mac = await self._async_resolve_mac()

            # Connect and start pairing
            await self._async_cleanup_client()
            self._tv = await self._async_create_client()

            try:
                connected = await self._tv.async_connect(timeout=TIMEOUT_CONNECT)
                if not connected:
                    return self.async_abort(reason="cannot_connect")

                device_info = await self._tv.async_get_device_info(timeout=5)
                if device_info:
                    self._name = device_info.get("tv_name") or self._name
                    self._model = device_info.get("model_name")
                    self._sw_version = device_info.get("tv_version")

                    info_mac = _extract_mac_from_device_info(device_info)
                    if info_mac:
                        self._mac = info_mac
                        self._device_id = self._mac

                await self._tv.async_start_pairing()
                await asyncio.sleep(1)

                return await self.async_step_pair()

            except Exception:
                _LOGGER.exception("Error connecting for SSDP pairing")
                await self._async_cleanup_client()
                return self.async_abort(reason="cannot_connect")

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._name,
                "host": self._host or "",
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        self._host = entry_data[CONF_HOST]
        self._port = entry_data.get(CONF_PORT, DEFAULT_PORT)
        self._mac = entry_data.get(CONF_MAC)
        self._device_id = entry_data.get(CONF_DEVICE_ID)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth and trigger pairing."""
        if user_input is not None:
            await self._async_cleanup_client()
            self._tv = await self._async_create_client()

            try:
                connected = await self._tv.async_connect(timeout=TIMEOUT_CONNECT)
                if not connected:
                    return self.async_abort(reason="cannot_connect")

                await self._tv.async_start_pairing()
                await asyncio.sleep(1)
                return await self.async_step_pair()

            except Exception:
                _LOGGER.exception("Error during reauth")
                await self._async_cleanup_client()
                return self.async_abort(reason="cannot_connect")

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"host": self._host or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return VidaaTVOptionsFlow()


class VidaaTVOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Vidaa TV."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get("scan_interval", SCAN_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=current_interval,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=300,
                            step=5,
                            mode=NumberSelectorMode.SLIDER,
                            unit_of_measurement="seconds",
                        )
                    ),
                }
            ),
        )
