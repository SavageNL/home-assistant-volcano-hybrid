"""Config flow for Volcano Hybrid integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class VolcanoHybridConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volcano Hybrid."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: BluetoothServiceInfoBleak | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = user_input["address"]
            name = user_input["name"]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data={"address": address})

        devices = async_discovered_service_info(self.hass, {"manufacturer_id": 1736})
        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(devices),
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle discovery initiated by Bluetooth."""
        _LOGGER.debug("Discovered device: %s", discovery_info)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered_device = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm the discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_device.name,
                data={"address": self._discovered_device.address},
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovered_device.name},
        )

    def _build_schema(self, devices: list) -> Any:
        """Build the schema for the config flow."""
        from homeassistant.helpers.selector import (
            SelectSelector,
            SelectSelectorConfig,
            SelectSelectorMode,
        )

        options = {device.address: device.name for device in devices}
        return {
            "address": SelectSelector(
                SelectSelectorConfig(
                    options=list(options.keys()),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            "name": SelectSelector(
                SelectSelectorConfig(
                    options=list(options.values()),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
