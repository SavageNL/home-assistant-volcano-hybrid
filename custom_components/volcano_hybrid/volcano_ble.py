"""Volcano Hybrid BLE communication module."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from bleak import BleakClient, BleakError, BLEDevice
from bleak.backends.service import BleakGATTService
from bleak_retry_connector import retry_bluetooth_connection_error
from habluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)


class VolcanoSensor(StrEnum):
    """Volcano sensor types."""

    VOLCANO = "volcano"
    CURRENT_AUTO_OFF_TIME = "current_auto_off_time"
    HEAT_TIME = "heat_time"
    SHUT_OFF = "shut_off"
    LED_BRIGHTNESS = "led_brightness"
    AUTO_SHUTDOWN = "auto_shutdown"
    PRV1_ERROR = "prv1_error"
    SHOWING_CELSIUS = "showing_celsius"
    DISPLAY_ON_COOLING = "display_on_cooling"
    PRV2_ERROR = "prv2_error"
    VIBRATION = "vibration"


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


class VolcanoHybridData:
    """Data object to hold Volcano Hybrid data."""

    def __init__(self) -> None:
        """Initialize the Volcano Hybrid data object."""
        self.current_temp: int = 0
        self.set_temp: int = 0
        self.available: bool = False

        self.serial_number: str = ""
        self.firmware_version: str = ""
        self.firmware_ble_version: str = ""
        self.bootloader_version: str = ""
        self.firmware: str = ""
        self._current_auto_off_time: int = 0
        self.heat_hours_changed: int = 0
        self.heat_minutes_changed: int = 0
        self.shut_off: int = 0
        self.led_brightness: int = 0

        # Prv1 attributes
        self.heater: bool = False
        self.fan: bool = False
        self.auto_shutdown: bool = False
        self.prv1_error: bool = False

        # Prv2 attributes
        self.showing_celcius: bool = False
        self.display_on_cooling: bool = False
        self.prv2_error: bool = False

        # Prv3 attributes
        self.vibration: bool = False

    @property
    def heat_time(self) -> int:
        """Get the current auto off time in minutes."""
        return self.heat_hours_changed * 60 + self.heat_minutes_changed

    @property
    def current_auto_off_time(self) -> int:
        """Get the current auto off time in minutes."""
        return self._current_auto_off_time if self._current_auto_off_time > 0 else None

    @current_auto_off_time.setter
    def current_auto_off_time(self, value: int) -> None:
        self._current_auto_off_time = value

    def get(self, key: str) -> Any:
        """Get the value of the specified key."""
        return getattr(self, key)


class VolcanoBLE:
    """Volcano BLE class."""

    def __init__(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
        *,
        device: BLEDevice = None,
    ) -> None:
        """Initialize VolcanoBLE."""
        self._after_data_updated = data_updated
        self._after_device_updated = device_updated
        self.client: BleakClient | None = None
        self.device = device
        self.data = VolcanoHybridData()

    def is_supported(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if the device is supported."""
        return STORZ_BICKEL_MANUFACTURER_ID in service_info.manufacturer_id

    async def async_update_from_device(self, device: BLEDevice) -> VolcanoHybridData:
        """Trigger an update of the Volcano device data."""
        if device and device != self.device:
            await self.async_disconnect()
            self.device = device
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
                await self._async_read_and_subscribe_all(initial=True)
        except BleakError:
            _LOGGER.exception("Failed to connect to BLE device")
            await self.async_disconnect()
            return False
        return True

    def _disconnected(self, client: BleakClient) -> None:
        """Handle disconnection events."""
        _LOGGER.debug("Disconnected from BLE device at %s", client.address)
        self.data.available = False
        self._after_data_updated()

    @retry_bluetooth_connection_error()
    async def _async_read_and_subscribe_all(
        self, initial: bool = False
    ) -> VolcanoHybridData:
        """Read all required characteristics from the BLE device."""
        try:

            def _read_current_temp(data: bytearray) -> None:
                self.data.current_temp = int(int.from_bytes(data, "little") / 10)
                self._after_data_updated()

            def _read_set_temp(data: bytearray) -> None:
                self.data.set_temp = int(int.from_bytes(data, "little") / 10)
                self._after_data_updated()

            def _read_prj1v(data: bytearray) -> None:
                prj1v = int.from_bytes(data, "little")
                self.data.heater = bool(prj1v & MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA)
                self.data.fan = bool(prj1v & MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE)
                self.data.auto_shutdown = bool(
                    prj1v & MASK_PRJSTAT1_VOLCANO_ENABLE_AUTOBLESHUTDOWN
                )
                self.data.prv1_error = bool(prj1v & MASK_PRJSTAT1_VOLCANO_ERR)
                self._after_data_updated()

            await asyncio.gather(
                self._async_read_and_subscribe(
                    SERVICE_UUID,
                    CHARACTERISTIC_CURRENT_TEMP,
                    _read_current_temp,
                    subscribe=initial,
                ),
                self._async_read_and_subscribe(
                    SERVICE_UUID,
                    CHARACTERISTIC_SET_TEMP,
                    _read_set_temp,
                    subscribe=initial,
                ),
                self._async_read_and_subscribe(
                    SERVICE3_UUID, CHARACTERISTIC_PRJ1V, _read_prj1v, subscribe=initial
                ),
            )

            if initial:
                await self._async_read_initial_characteristics()
            self.data.available = True
        except BleakError:
            _LOGGER.exception("Error reading characteristics")
        return self.data

    async def _async_read_initial_characteristics(self) -> None:
        def _parse_prj2v(data: bytearray) -> None:
            prj2v = int.from_bytes(data, "little")
            self.data.showing_celcius = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA == 0
            )
            self.data.display_on_cooling = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING == 0
            )
            self.data.prv2_error = bool(prj2v & MASK_PRJSTAT2_VOLCANO_ERR)
            self._after_data_updated()

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

        def _parse_current_auto_off_time(data: bytearray) -> None:
            self.data.current_auto_off_time = int.from_bytes(data, "little") / 60
            self._after_data_updated()

        def _parse_heat_hours_changed(data: bytearray) -> None:
            self.data.heat_hours_changed = int.from_bytes(data, "little")
            self._after_data_updated()

        def _parse_heat_minutes_changed(data: bytearray) -> None:
            self.data.heat_minutes_changed = int.from_bytes(data, "little")
            self._after_data_updated()

        def _parse_shut_off(data: bytearray) -> None:
            self.data.shut_off = int(int.from_bytes(data, "little") / 60)

        def _parse_led_brightness(data: bytearray) -> None:
            self.data.led_brightness = int.from_bytes(data, "little")

        await asyncio.gather(
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
        self._after_device_updated()

    async def async_set_fan(self, on: bool) -> None:
        """Set the fan on or off."""
        _LOGGER.debug("Setting fan to %s", on)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_FAN_ON if on else CHARACTERISTIC_FAN_OFF,
            bytearray([int(on)]),
        )
        self.data.fan = on
        self._after_data_updated()

    async def async_set_heater(self, on: bool) -> None:
        """Set the heater on or off."""
        _LOGGER.debug("Setting heater to %s", on)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_HEATER_ON if on else CHARACTERISTIC_HEATER_OFF,
            bytearray([int(on)]),
        )
        self.data.heater = on
        self._after_data_updated()

    async def async_set_target_temperature(self, target: float) -> None:
        """Set the target temperature."""
        _LOGGER.debug("Setting temperature to %s", target)
        await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_SET_TEMP,
            bytearray(int.to_bytes(int(target * 10), 2, "little")),
        )
        self.data.set_temp = int(target)
        self._after_data_updated()

    async def async_set_showing_celcius(self, on: bool) -> None:
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

    async def _async_read_and_subscribe(
        self,
        service: str,
        characteristic: str,
        value_change_callback: Callable[[bytearray], None],
        subscribe: bool,
    ) -> None:
        """Read a characteristic from the BLE device."""
        if not await self._ensure_client_connected():
            return

        service: BleakGATTService = self.client.services.get_service(service)
        char = service.get_characteristic(characteristic)
        if subscribe:
            await self.client.start_notify(
                char, lambda _, data: value_change_callback(data)
            )
        value_change_callback(await self.client.read_gatt_char(char))

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
