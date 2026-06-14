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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AUTO_CONNECT_DELAY,
    CONF_DELAYED_RECONNECT_DELAY,
    DEFAULT_AUTO_CONNECT_DELAY,
    DEFAULT_DELAYED_RECONNECT_DELAY,
    DOMAIN,
)
from .volcano_ble import VolcanoBLE, VolcanoHybridData

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from datetime import datetime

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
        # Whether the integration may connect on its own. Disabling this frees
        # the device so other Bluetooth clients can use it; commands and the
        # manual reconnect buttons still connect on demand.
        self.auto_connect = True
        self._connect_timer: CALLBACK_TYPE | None = None

    @property
    def auto_connect_delay(self) -> float:
        """Seconds to wait before auto-connecting after seeing the device."""
        return float(
            self.config_entry.options.get(
                CONF_AUTO_CONNECT_DELAY, DEFAULT_AUTO_CONNECT_DELAY
            )
        )

    @property
    def delayed_reconnect_delay(self) -> float:
        """Seconds the delayed reconnect button stays disconnected."""
        return float(
            self.config_entry.options.get(
                CONF_DELAYED_RECONNECT_DELAY, DEFAULT_DELAYED_RECONNECT_DELAY
            )
        )

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

        @callback
        def _on_advertisement(
            service_info: BluetoothServiceInfoBleak, _: BluetoothChange
        ) -> None:
            # Reflect the live signal, then schedule a connect. Scheduling
            # (rather than connecting on this advertisement) collapses a
            # power-on burst into one attempt and gives every Bluetooth proxy
            # a moment to report so the best path is chosen.
            self._device.device_rssi = service_info.rssi
            if self.auto_connect and not self._device.is_connected:
                self._schedule_connect(self.auto_connect_delay)

        self.config_entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                _on_advertisement,
                BluetoothCallbackMatcher(connectable=True, address=self.address),
                BluetoothScanningMode.ACTIVE,
            )
        )
        # Make sure a scheduled connect never outlives the entry.
        self.config_entry.async_on_unload(self._cancel_connect_timer)

    @callback
    def _schedule_connect(self, delay: float, *, force: bool = False) -> None:
        """
        Schedule a single connect attempt after a delay.

        A non-forced call is a no-op while one is already pending, so an
        advertisement burst results in only one attempt. A forced call
        (manual reconnect) replaces any pending attempt and ignores the
        auto-connect setting.
        """
        if force:
            self._cancel_connect_timer()
        elif self._connect_timer is not None:
            return

        async def _connect(_now: datetime) -> None:
            self._connect_timer = None
            if not force and (not self.auto_connect or self._device.is_connected):
                return
            await self._async_refresh_device(connect=True)

        self._connect_timer = async_call_later(self.hass, delay, _connect)

    @callback
    def _cancel_connect_timer(self) -> None:
        """Cancel a pending scheduled connect, if any."""
        if self._connect_timer is not None:
            self._connect_timer()
            self._connect_timer = None

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        self._cancel_connect_timer()
        await self._device.async_disconnect()

    async def _async_update_data(self) -> VolcanoHybridData:
        """Reconnect/refresh on the coordinator interval (a fallback poll)."""
        await self._async_refresh_device(connect=self.auto_connect)
        return self._device.data

    async def _async_refresh_device(self, *, connect: bool) -> None:
        """Refresh the device, optionally (re)connecting to it."""
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, True)

        last_info = bluetooth.async_last_service_info(self.hass, self.address)
        if last_info:
            self._device.device_rssi = last_info.rssi

        if device and (connect or self._device.is_connected):
            await self._device.async_manual_update(device)

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
        """Reconnect immediately, regardless of the auto-connect setting."""
        self._cancel_connect_timer()
        await self._device.async_disconnect()
        await self._async_refresh_device(connect=True)

    async def delayed_reconnect(self) -> None:
        """
        Disconnect, then reconnect after the configured delay.

        Staying disconnected lets the device advertise again so a better path
        can be picked, even when auto-connect is disabled.
        """
        await self._device.async_disconnect()
        self._schedule_connect(self.delayed_reconnect_delay, force=True)

    async def async_set_auto_connect(self, *, enabled: bool) -> None:
        """Enable or disable automatic connecting."""
        self.auto_connect = enabled
        if enabled:
            self._schedule_connect(self.auto_connect_delay)
        else:
            # Release the device so other Bluetooth clients can reach it.
            self._cancel_connect_timer()
            await self._device.async_disconnect()
        self.async_update_listeners()
