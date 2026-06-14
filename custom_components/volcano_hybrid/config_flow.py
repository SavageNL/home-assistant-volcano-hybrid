"""Config flow for Volcano Hybrid integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_AUTO_CONNECT_DELAY,
    CONF_DELAYED_RECONNECT_DELAY,
    DEFAULT_AUTO_CONNECT_DELAY,
    DEFAULT_DELAYED_RECONNECT_DELAY,
    DOMAIN,
)
from .volcano_ble import VolcanoBLE

_LOGGER = logging.getLogger(__name__)


class VolcanoHybridConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volcano Hybrid."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> VolcanoHybridOptionsFlow:
        """Return the options flow handler."""
        return VolcanoHybridOptionsFlow()

    def _async_discover_devices(self, *, allowed_address: str | None = None) -> None:
        """Collect supported devices that are not configured in another entry."""
        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(
            self.hass, connectable=True
        ):
            address = discovery_info.address
            if (
                address in current_addresses and address != allowed_address
            ) or address in self._discovered_devices:
                continue
            if VolcanoBLE.is_supported(discovery_info):
                self._discovered_devices[address] = discovery_info.name

    def _device_selection_schema(self) -> vol.Schema:
        """Build a schema with a dropdown of the discovered devices."""
        return vol.Schema(
            {
                vol.Required(CONF_ADDRESS): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=address, label=f"{name} ({address})")
                            for address, name in self._discovered_devices.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered_devices[address],
                data={CONF_ADDRESS: address},
            )

        self._async_discover_devices()
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=self._device_selection_schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address != entry.unique_id:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(
                entry,
                unique_id=address,
                title=self._discovered_devices[address],
                data={CONF_ADDRESS: address},
            )

        self._async_discover_devices(allowed_address=entry.data[CONF_ADDRESS])
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._device_selection_schema(),
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle discovery initiated by Bluetooth."""
        _LOGGER.debug("Discovered device: %s", discovery_info)
        if not VolcanoBLE.is_supported(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered_device = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered device."""
        if self._discovered_device is None:
            return self.async_abort(reason="no_devices_found")
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_device.name,
                data={CONF_ADDRESS: self._discovered_device.address},
            )

        self._set_confirm_only()
        placeholders = {"name": self._discovered_device.name}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
        )


class VolcanoHybridOptionsFlow(OptionsFlow):
    """Handle the options for a Volcano Hybrid entry."""

    def _options_schema(self) -> vol.Schema:
        """Build the options schema, defaulting to the current values."""
        options = self.config_entry.options
        delay_selector = NumberSelector(
            NumberSelectorConfig(
                min=0,
                step=0.5,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        )
        return vol.Schema(
            {
                vol.Required(
                    CONF_AUTO_CONNECT_DELAY,
                    default=options.get(
                        CONF_AUTO_CONNECT_DELAY, DEFAULT_AUTO_CONNECT_DELAY
                    ),
                ): delay_selector,
                vol.Required(
                    CONF_DELAYED_RECONNECT_DELAY,
                    default=options.get(
                        CONF_DELAYED_RECONNECT_DELAY, DEFAULT_DELAYED_RECONNECT_DELAY
                    ),
                ): delay_selector,
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self._options_schema(),
        )
