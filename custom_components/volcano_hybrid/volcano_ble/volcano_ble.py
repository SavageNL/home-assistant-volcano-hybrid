"""Volcano Hybrid BLE communication module."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, TypeVar

from bleak import BleakClient, BleakError, BleakGATTCharacteristic, BLEDevice
from bleak.backends.service import BleakGATTService
from habluetooth import BluetoothServiceInfoBleak

from .volcano_hybrid_data import VolcanoHybridData, VolcanoHybridDataStatusProvider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")
STORZ_BICKEL_MANUFACTURER_ID = 1736

# BLE service and characteristic placeholders
SERVICE_UUID = "10110000-5354-4f52-5a26-4249434b454c"
CHARACTERISTIC_CURRENT_TEMP = "10110001-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_SET_TEMP = "10110003-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_FAN_ON = "10110013-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_FAN_OFF = "10110014-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_HEATER_ON = "1011000f-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_HEATER_OFF = "10110010-5354-4f52-5a26-4249434b454c"  # 4

CHARACTERISTIC_CURRENT_AUTO_OFF_TIME = "1011000c-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_HEAT_HOURS_CHANGED = "10110015-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_HEAT_MINUTES_CHANGED = "10110016-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_SHUT_OFF = "1011000d-5354-4f52-5a26-4249434b454c"  # 4
CHARACTERISTIC_LED_BRIGHTNESS = "10110005-5354-4f52-5a26-4249434b454c"  # 4

# Status
SERVICE3_UUID = "10100000-5354-4f52-5a26-4249434b454c"
CHARACTERISTIC_PRJ1V = "1010000c-5354-4f52-5a26-4249434b454c"
CHARACTERISTIC_PRJ2V = "1010000d-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_PRJ3V = "1010000e-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_SERIAL_NUMBER = "10100008-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE_VERSION = "10100005-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE_BLE_VERSION = "10100004-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_BOOTLOADER_VERSION = "10100001-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE = "10100003-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_HIST1 = "10100015-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_HIST2 = "10100016-5354-4f52-5a26-4249434b454c"  # 3

MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA = 32
MASK_PRJSTAT1_VOLCANO_ENABLE_AUTOBLESHUTDOWN = 512
MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE = 8192
MASK_PRJSTAT1_VOLCANO_ERR = 16408
MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA = 512
MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING = 4096
MASK_PRJSTAT2_VOLCANO_ERR = 59
MASK_PRJSTAT3_VOLCANO_VIBRATION = 1024


class VolcanoBLE(VolcanoHybridDataStatusProvider):
    """Volcano BLE class."""

    def __init__(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
        *,
        device: BLEDevice = None,
    ) -> None:
        """Initialize VolcanoBLE."""
        super().__init__()
        self._after_data_updated = data_updated
        self._after_device_updated = device_updated
        self.client: BleakClient | None = None
        self.device = device
        self.data = VolcanoHybridData(self)

    @staticmethod
    def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if the device is supported."""
        return (
            STORZ_BICKEL_MANUFACTURER_ID == service_info.manufacturer_id
            and "VOLCANO H" in service_info.name
        )

    @property
    def rssi(self) -> int:
        """Get the device rssi."""
        return self.device.rssi

    def is_connected(self) -> bool:
        """Return True if the device is connected."""
        return bool(self.client and self.client.is_connected)

    async def async_manual_update(self, device: BLEDevice) -> VolcanoHybridData:
        """Trigger an update of the Volcano device data."""
        if device and device != self.device:
            await self.async_disconnect()
            self.device = device
            self._after_data_updated()

        # This will update when not connected yet
        await self._ensure_client_connected()
        return self.data

    async def _ensure_client_connected(self) -> bool:
        """Ensure the BLE client is initialized and connected."""
        try:
            if not self.device:
                _LOGGER.error("No last service info available, unable to connect")
                return False

            if not self.client:
                self.client = BleakClient(self.device, self._disconnected)
            if not self.client.is_connected:
                _LOGGER.debug("Connecting to BLE device at %s", self.device.address)
                await self.client.connect()
                self._after_data_updated()
                await self._async_read_and_subscribe_all()
        except BleakError as err:
            _LOGGER.debug("Failed to connect to BLE device: %s", err)
            await self.async_disconnect()
            return False
        return True

    def _disconnected(self, client: BleakClient) -> None:
        """Handle disconnection events."""
        _LOGGER.debug("Disconnected from BLE device at %s", client.address)
        self._after_data_updated()

    async def _async_read_and_subscribe_all(self) -> VolcanoHybridData:
        """Read all required characteristics from the BLE device."""
        try:
            await self._async_read_initial_characteristics()
        except BleakError:
            _LOGGER.exception("Error reading characteristics")
        return self.data

    async def _async_read_set_temp(self, *, subscribe: bool = False) -> int:
        def _read_set_temp_inner(data: bytearray) -> int:
            self.data.set_temp = int(int.from_bytes(data, "little") / 10)
            return self.data.set_temp

        return await self._async_read_and_subscribe(
            SERVICE_UUID,
            CHARACTERISTIC_SET_TEMP,
            _read_set_temp_inner,
            subscribe=subscribe,
        )

    async def _async_read_prj1v(self, *, subscribe: bool = False) -> None:
        def _read_prj1v_inner(data: bytearray) -> None:
            prj1v = int.from_bytes(data, "little")
            self.data.heater = bool(prj1v & MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA)
            self.data.fan = bool(prj1v & MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE)
            self.data.auto_shutdown = bool(
                prj1v & MASK_PRJSTAT1_VOLCANO_ENABLE_AUTOBLESHUTDOWN
            )
            self.data.prv1_error = bool(prj1v & MASK_PRJSTAT1_VOLCANO_ERR)

        (
            await self._async_read_and_subscribe(
                SERVICE3_UUID,
                CHARACTERISTIC_PRJ1V,
                _read_prj1v_inner,
                subscribe=subscribe,
            ),
        )

    async def _async_read_initial_characteristics(self) -> None:
        def _read_current_temp(data: bytearray) -> None:
            self.data.current_temp = int(int.from_bytes(data, "little") / 10)

        def _parse_prj2v(data: bytearray) -> None:
            prj2v = int.from_bytes(data, "little")
            self.data.showing_celsius = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA == 0
            )
            self.data.display_on_cooling = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING == 0
            )
            self.data.prv2_error = bool(prj2v & MASK_PRJSTAT2_VOLCANO_ERR)

        def _parse_prj3v(data: bytearray) -> None:
            prj3v = int.from_bytes(data, "little")
            self.data.vibration = bool(prj3v & MASK_PRJSTAT3_VOLCANO_VIBRATION == 0)

        def _parse_serial_number(data: bytearray) -> None:
            self.data.serial_number = data.decode("utf-8").strip()

        def _parse_firmware_version(data: bytearray) -> None:
            self.data.firmware_version = data.decode("utf-8").strip()

        def _parse_firmware_ble_version(data: bytearray) -> None:
            self.data.firmware_ble_version = data.decode("utf-8").strip()

        def _parse_bootloader_version(data: bytearray) -> None:
            self.data.bootloader_version = data.decode("utf-8").strip()

        def _parse_firmware(data: bytearray) -> None:
            self.data.firmware = data.decode("utf-8").strip()

        async def _parse_current_auto_off_time(data: bytearray) -> None:
            self.data.current_auto_off_time = int.from_bytes(data, "little") / 60
            await self._async_try_ensure_written_values()

        def _parse_heat_hours_changed(data: bytearray) -> None:
            self.data.heat_hours_changed = int.from_bytes(data, "little")

        def _parse_heat_minutes_changed(data: bytearray) -> None:
            self.data.heat_minutes_changed = int.from_bytes(data, "little")

        def _parse_shut_off(data: bytearray) -> None:
            self.data.shut_off = int(int.from_bytes(data, "little") / 60)

        def _parse_led_brightness(data: bytearray) -> None:
            self.data.led_brightness = int.from_bytes(data, "little")

        async def _async_read_set_temp_and_subscribe() -> None:
            await self._async_read_set_temp(subscribe=True)

        await self._async_read_prj1v(subscribe=True)  # Ensure on-state is correct
        await asyncio.gather(
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_CURRENT_TEMP,
                _read_current_temp,
                subscribe=True,
            ),
            _async_read_set_temp_and_subscribe(),
            self._async_read_and_subscribe(
                SERVICE3_UUID,
                CHARACTERISTIC_SERIAL_NUMBER,
                _parse_serial_number,
                subscribe=False,
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID,
                CHARACTERISTIC_FIRMWARE_VERSION,
                _parse_firmware_version,
                subscribe=False,
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID,
                CHARACTERISTIC_FIRMWARE_BLE_VERSION,
                _parse_firmware_ble_version,
                subscribe=False,
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID,
                CHARACTERISTIC_BOOTLOADER_VERSION,
                _parse_bootloader_version,
                subscribe=False,
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID, CHARACTERISTIC_FIRMWARE, _parse_firmware, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID, CHARACTERISTIC_PRJ2V, _parse_prj2v, subscribe=True
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID, CHARACTERISTIC_PRJ3V, _parse_prj3v, subscribe=True
            ),
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_CURRENT_AUTO_OFF_TIME,
                _parse_current_auto_off_time,
                subscribe=True,
            ),
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_HEAT_HOURS_CHANGED,
                _parse_heat_hours_changed,
                subscribe=True,
            ),
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_HEAT_MINUTES_CHANGED,
                _parse_heat_minutes_changed,
                subscribe=True,
            ),
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_SHUT_OFF,
                _parse_shut_off,
                subscribe=False,
            ),
            self._async_read_and_subscribe(
                SERVICE_UUID,
                CHARACTERISTIC_LED_BRIGHTNESS,
                _parse_led_brightness,
                subscribe=False,
            ),
        )
        _LOGGER.debug("Initial characteristics read complete")
        self._after_data_updated()
        self._after_device_updated()

    async def async_set_fan(self, on: bool) -> None:
        """Set the fan on or off."""
        _LOGGER.debug("Setting fan to %s", on)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_FAN_ON if on else CHARACTERISTIC_FAN_OFF,
            bytearray([int(on)]),
        )
        self.data.fan_write = on
        self._after_data_updated()

    async def async_set_heater(self, on: bool) -> None:
        """Set the heater on or off."""
        _LOGGER.debug("Setting heater to %s", on)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_HEATER_ON if on else CHARACTERISTIC_HEATER_OFF,
            bytearray([int(on)]),
        )
        self.data.heater_write = on
        self._after_data_updated()

    async def async_set_target_temperature(self, target: float) -> None:
        """Set the target temperature."""
        _LOGGER.debug("Setting temperature to %s", target)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_SET_TEMP,
            bytearray(int.to_bytes(int(target * 10), 2, "little")),
        )
        await self._async_read_set_temp()
        self.data.set_temp_write = int(target)
        self._after_data_updated()

    async def async_set_showing_celsius(self, on: bool) -> None:
        """Set the toggle for showing Celsius."""
        if on:
            await self._write_register_2(MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA)
        else:
            await self._write_register_2(65536 + MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA)

    async def async_set_display_on_cooling(self, on: bool) -> None:
        """Set the toggle for display on cooling."""
        if on:
            await self._write_register_2(MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING)
        else:
            await self._write_register_2(
                65536 + MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING
            )

    async def _write_register_2(self, mask: int) -> None:
        """Write to register 2."""
        await self._write_gatt(
            SERVICE3_UUID,
            CHARACTERISTIC_PRJ2V,
            bytearray(int.to_bytes(mask, 4, "little")),
        )

    async def async_set_vibration(self, on: bool) -> None:
        """Set the toggle for vibration."""
        if on:
            await self._write_register_3(MASK_PRJSTAT3_VOLCANO_VIBRATION)
        else:
            await self._write_register_3(65536 + MASK_PRJSTAT3_VOLCANO_VIBRATION)

    async def _write_register_3(self, mask: int) -> None:
        """Write to register 2."""
        await self._write_gatt(
            SERVICE3_UUID,
            CHARACTERISTIC_PRJ3V,
            bytearray(int.to_bytes(mask, 4, "little")),
        )

    async def async_set_shut_off(self, minutes: int) -> None:
        """Set the toggle for shut off."""
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_SHUT_OFF,
            bytearray(int.to_bytes(minutes * 60, 2, "little")),
        )
        self.data.shut_off = minutes
        self._after_data_updated()

    async def async_set_led_brightness(self, brightness: int) -> None:
        """Set the LED brightness."""
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_LED_BRIGHTNESS,
            bytearray(int.to_bytes(brightness, 2, "little")),
        )
        self.data.led_brightness = brightness
        self._after_data_updated()

    async def async_disconnect(self) -> None:
        """Disconnect from the Volcano device."""
        if self.client:
            if self.client.is_connected:
                await self.client.disconnect()
            self.client = None
            self._after_data_updated()

    async def _async_read_and_subscribe(
        self,
        service: str,
        characteristic: str,
        value_change_callback: Callable[[bytearray], Awaitable[T] | T],
        subscribe: bool,
    ) -> T:
        """Read a characteristic from the BLE device."""
        if not self.is_connected():
            return None

        async def _async_call_callback(data: bytearray) -> None:
            if inspect.iscoroutinefunction(value_change_callback):
                await value_change_callback(data)
            else:
                value_change_callback(data)

        service: BleakGATTService = self.client.services.get_service(service)
        char = service.get_characteristic(characteristic)
        current_value = await self.client.read_gatt_char(char)
        if (
            subscribe and self.is_connected()
        ):  # We just awaited a read, we could be disconnected now
            try:

                async def _async_callback(
                    _: BleakGATTCharacteristic, data: bytearray
                ) -> None:
                    await _async_call_callback(data)
                    self._after_data_updated()

                await self.client.start_notify(char, _async_callback)
            except BleakError:
                await self.async_disconnect()

        return await _async_call_callback(current_value)

    async def _write_gatt(
        self,
        service: str,
        characteristic: str,
        value: bytearray,
    ) -> None:
        """Write to the GATT characteristic."""
        if not await self._ensure_client_connected():
            return

        service: BleakGATTService = self.client.services.get_service(service)
        char = service.get_characteristic(characteristic)
        await self.client.write_gatt_char(
            char,
            value,
        )

    async def _async_try_ensure_written_values(self) -> None:
        """Ensure that the pending writes are written to the device."""
        await self._async_read_set_temp()
        if (
            self.data.fan_needs_write
            or self.data.heater_needs_write
            or self.data.set_temp_needs_write
        ):
            await self._async_read_prj1v()
            if not self.data.is_on:
                # We don't want to turn on the device after dropping commands
                self.data.clear_open_writes()

        if self.data.fan_needs_write:
            await self.async_set_fan(self.data.fan_write)

        if self.data.heater_needs_write:
            await self.async_set_heater(self.data.heater_write)

        if self.data.set_temp_needs_write:
            await self.async_set_target_temperature(self.data.set_temp_write)
