"""Coordinator for Volcano Hybrid BLE device."""

from __future__ import annotations

import logging
from datetime import timedelta

from habluetooth import BluetoothScanningMode
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothChange
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .volcano_ble import VolcanoBLE, VolcanoHybridData

_LOGGER = logging.getLogger(__name__)


class VolcanoHybridCoordinator(DataUpdateCoordinator[VolcanoHybridData]):
    """My custom coordinator."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, address: str
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Volcano Hybrid",
            config_entry=config_entry,
            update_interval=timedelta(seconds=60),
            always_update=True,
        )

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name="Volcano Hybrid",
            manufacturer="Storz & Bickel",
            model="Volcano Hybrid",
            connections={(CONNECTION_BLUETOOTH, address)},
        )
        self._device = VolcanoBLE(self.async_update_listeners, self.update_device)
        self.data = self._device.data
        self.address = address

    async def async_config_entry_first_refresh(self) -> None:
        """Ensure that the config entry is ready."""
        try:
            await super().async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.debug(
                "Config entry is determined not to be ready, but "
                "that's because we can't connect. We will connect "
                "later and are ready now."
            )

    async def _async_setup(self) -> None:
        """Connect as soon as possible."""

        def callback(_: BluetoothServiceInfoBleak, __: BluetoothChange) -> None:
            self.hass.async_create_task(self._async_update_data())

        self.config_entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                callback,
                BluetoothCallbackMatcher(connectable=True, address=self.address),
                BluetoothScanningMode.ACTIVE,
            )
        )

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        await self._device.async_disconnect()

    async def _async_update_data(self) -> VolcanoHybridData:
        """Fetch data from API endpoint."""
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, True)
        if device:
            await self._device.async_manual_update(device)
        return self._device.data

    def async_update_listeners(self) -> None:
        """Update listeners."""
        self.last_update_success = self._device.is_connected()
        super().async_update_listeners()

    def update_device(self) -> None:
        """Update the device registry with the latest data."""
        dev_reg = dr.async_get(self.hass)
        device_id = dev_reg.async_get_device(self.device_info.get("identifiers")).id
        dr.async_get(self.hass).async_update_device(
            device_id=device_id,
            serial_number=self.data.serial_number,
            sw_version=self.data.firmware_version,
            hw_version=self.data.bootloader_version,
        )

    async def set_fan(self, on: bool) -> None:
        """Set the fan on or off."""
        await self._device.async_set_fan(on)

    async def set_heater(self, on: bool) -> None:
        """Set the heater on or off."""
        await self._device.async_set_heater(on)

    async def set_target_temperature(self, target: float) -> None:
        """Set the target temperature."""
        await self._device.async_set_target_temperature(target)

    async def set_showing_celsius(self, on: bool) -> None:
        """Set the toggle for showing Celsius."""
        await self._device.async_set_showing_celsius(on)

    async def set_display_on_cooling(self, on: bool) -> None:
        """Set the toggle for display on cooling."""
        await self._device.async_set_display_on_cooling(on)

    async def set_vibration(self, on: bool) -> None:
        """Set the toggle for vibration."""
        await self._device.async_set_vibration(on)

    async def set_shut_off(self, minutes: float) -> None:
        """Set the toggle for shut off."""
        await self._device.async_set_shut_off(int(minutes))

    async def set_led_brightness(self, brightness: float) -> None:
        """Set the LED brightness."""
        await self._device.async_set_led_brightness(int(brightness))

    async def reconnect(self) -> None:
        """Attempt to reconnect."""
        await self._device.async_disconnect()
        await self._async_update_data()
