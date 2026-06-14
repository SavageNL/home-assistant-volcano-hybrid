"""Coordinator for Volcano Hybrid BLE device."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakError
from habluetooth import BluetoothScanningMode
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothChange
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .volcano_ble import VolcanoBLE, VolcanoHybridData

if TYPE_CHECKING:
    from collections.abc import Awaitable

_LOGGER = logging.getLogger(__name__)

type VolcanoHybridConfigEntry = ConfigEntry[VolcanoHybridCoordinator]


class VolcanoHybridCoordinator(DataUpdateCoordinator[VolcanoHybridData]):
    """Coordinator that maintains the BLE connection and pushes device updates."""

    config_entry: VolcanoHybridConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: VolcanoHybridConfigEntry,
        address: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Volcano Hybrid",
            config_entry=config_entry,
            update_interval=timedelta(seconds=10),
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
        self._was_connected = False

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
            # Request a debounced, serialized refresh rather than spawning a
            # task per advertisement. A power-on advertisement burst would
            # otherwise launch many concurrent connection attempts.
            self.config_entry.async_create_task(
                self.hass, self.async_request_refresh()
            )

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

        last_info = bluetooth.async_last_service_info(self.hass, self.address)
        if last_info:
            self._device.device_rssi = last_info.rssi

        if device:
            await self._device.async_manual_update(device)
        return self._device.data

    def async_update_listeners(self) -> None:
        """Update listeners."""
        connected = self._device.is_connected
        if connected != self._was_connected:
            if connected:
                _LOGGER.info("Connected to the Volcano Hybrid at %s", self.address)
            else:
                _LOGGER.info(
                    "Connection to the Volcano Hybrid at %s lost", self.address
                )
            self._was_connected = connected
        self.last_update_success = connected
        super().async_update_listeners()

    def update_device(self) -> None:
        """Update the device registry with the latest data."""
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(self.device_info.get("identifiers"))
        if not device:
            return

        dev_reg.async_update_device(
            device_id=device.id,
            serial_number=self.data.serial_number,
            sw_version=self.data.firmware_version,
            hw_version=self.data.bootloader_version,
        )

    async def _async_command(self, command: Awaitable[bool]) -> None:
        """Run a device command, raising HomeAssistantError when it fails."""
        try:
            written = await command
        except BleakError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
            ) from err
        if not written:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
            )

    async def set_fan(self, on: bool) -> None:
        """Set the fan on or off."""
        await self._async_command(self._device.async_set_fan(on))

    async def set_heater(self, on: bool) -> None:
        """Set the heater on or off."""
        await self._async_command(self._device.async_set_heater(on))

    async def set_target_temperature(self, target: float) -> None:
        """Set the target temperature."""
        await self._async_command(self._device.async_set_target_temperature(target))

    async def set_showing_celsius(self, on: bool) -> None:
        """Set the toggle for showing Celsius."""
        await self._async_command(self._device.async_set_showing_celsius(on))

    async def set_display_on_cooling(self, on: bool) -> None:
        """Set the toggle for display on cooling."""
        await self._async_command(self._device.async_set_display_on_cooling(on))

    async def set_vibration(self, on: bool) -> None:
        """Set the toggle for vibration."""
        await self._async_command(self._device.async_set_vibration(on))

    async def set_shut_off(self, minutes: float) -> None:
        """Set the shut off time in minutes."""
        await self._async_command(self._device.async_set_shut_off(int(minutes)))

    async def set_led_brightness(self, brightness: float) -> None:
        """Set the LED brightness."""
        await self._async_command(
            self._device.async_set_led_brightness(int(brightness))
        )

    async def reconnect(self) -> None:
        """Attempt to reconnect."""
        await self._device.async_disconnect()
        await self._async_update_data()
