"""Volcano Hybrid BLE communication module."""

from __future__ import annotations

import asyncio
import logging

# The manufacturer id is re-exported: tests import it from this module.
from .const import STORZ_BICKEL_MANUFACTURER_ID, DeviceFamily  # noqa: F401
from .device import StorzBickelDevice, _decode_ascii
from .volcano_hybrid_data import VolcanoHybridData

_LOGGER = logging.getLogger(__name__)
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
# The controller keeps five status words; these two carry the other two
# (VOLCANO_BLE_SPEC.md §1). A GATT dump of a V01.03 device confirms both are
# served — 1010000f as read/write/notify, 10100010 as read/notify — but
# nothing decodes their contents yet, so they are read as raw diagnostics
# only. Read without subscribing, and a device that does not serve them (an
# older module revision) is not treated as an error.
CHARACTERISTIC_PRJ4V = "1010000f-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_PRJ5V = "10100010-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_SERIAL_NUMBER = "10100008-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE_VERSION = "10100005-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE_BLE_VERSION = "10100004-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_BOOTLOADER_VERSION = "10100001-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_FIRMWARE = "10100003-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_HIST1 = "10100015-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_HIST2 = "10100016-5354-4f52-5a26-4249434b454c"  # 3
# Two fixed identity strings the device names itself with: `HYBRID` and
# `230VAC` on a V01.03 device (VOLCANO_BLE_SPEC.md §3). Both advertise write —
# nothing here writes them, since what a device calls itself and what mains it
# was built for are facts about the hardware, not settings. Read without
# subscribing, and tolerated as missing: they are served by the BLE module, so
# another module revision may not offer them.
CHARACTERISTIC_MAINS_VOLTAGE = "10100006-5354-4f52-5a26-4249434b454c"  # 3
CHARACTERISTIC_MODEL = "10100007-5354-4f52-5a26-4249434b454c"  # 3

MASK_PRJSTAT1_VOLCANO_ACTUATOR_FAULT = 16
MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA = 32
MASK_PRJSTAT1_VOLCANO_ENABLE_AUTOBLESHUTDOWN = 512
MASK_PRJSTAT1_VOLCANO_TEMPERATURE_REACHED = 1024
MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE = 8192
MASK_PRJSTAT1_VOLCANO_ERR = 16408
MASK_PRJSTAT2_VOLCANO_SERVICE_MODE = 64
MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA = 512
MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING = 4096
MASK_PRJSTAT2_VOLCANO_ERR = 59
MASK_PRJSTAT3_VOLCANO_VIBRATION = 1024


class VolcanoDevice(StorzBickelDevice):
    """Volcano BLE class."""

    family = DeviceFamily.VOLCANO_HYBRID
    data_class = VolcanoHybridData
    data: VolcanoHybridData

    async def _async_refresh(self) -> None:
        # Re-read the current temperature rather than trusting the
        # subscription. Notifications are unacknowledged, so a dropped one
        # leaves a stale reading that nothing else corrects: the device only
        # notifies when the value changes, and while it holds a temperature it
        # barely changes. This poll is the fallback that repairs that.
        await self._async_read_current_temp()

    async def _async_read_set_temp(self, *, subscribe: bool = False) -> None:
        def _read_set_temp_inner(data: bytearray) -> None:
            self.data.set_temp = int(int.from_bytes(data, "little") / 10)

        await self._async_read_and_subscribe(
            SERVICE_UUID,
            CHARACTERISTIC_SET_TEMP,
            _read_set_temp_inner,
            subscribe=subscribe,
        )

    async def _async_read_prj1v(self, *, subscribe: bool = False) -> None:
        def _read_prj1v_inner(data: bytearray) -> None:
            prj1v = int.from_bytes(data, "little")
            self.data.prj1 = prj1v
            self.data.heater = bool(prj1v & MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA)
            self.data.fan = bool(prj1v & MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE)
            # Bit 9. The name is historical ("auto BLE shutdown armed"); per
            # spec §3.1 it means the target has been reached at least once this
            # heating cycle. That is what gates the start of the heater auto-off
            # countdown, which is why the entity is named after the countdown.
            # It has no clear path of its own: only switching the heater off
            # (which wipes the register) resets it.
            self.data.auto_shutdown = bool(
                prj1v & MASK_PRJSTAT1_VOLCANO_ENABLE_AUTOBLESHUTDOWN
            )
            # Bit 10, a latch: set the moment the reading reaches the target,
            # cleared only by raising the target 3 °C or more above the
            # previous one, and wiped when the heater goes off (spec §3.1.1).
            self.data.at_temperature = bool(
                prj1v & MASK_PRJSTAT1_VOLCANO_TEMPERATURE_REACHED
            )
            # Bit 4: a timing fault in the heater state machine, logged as code
            # 0x3D, which inhibits both the heater and the pump. What the
            # firmware times is not established, so spec §7 says to report it as
            # a timing fault rather than name a physical cause for it.
            self.data.actuator_fault = bool(
                prj1v & MASK_PRJSTAT1_VOLCANO_ACTUATOR_FAULT
            )
            self.data.prv1_error = bool(prj1v & MASK_PRJSTAT1_VOLCANO_ERR)

        await self._async_read_and_subscribe(
            SERVICE3_UUID,
            CHARACTERISTIC_PRJ1V,
            _read_prj1v_inner,
            subscribe=subscribe,
        )

    async def _async_read_current_temp(self, *, subscribe: bool = False) -> None:
        def _read_current_temp_inner(data: bytearray) -> None:
            self.data.current_temp = int(int.from_bytes(data, "little") / 10)

        await self._async_read_and_subscribe(
            SERVICE_UUID,
            CHARACTERISTIC_CURRENT_TEMP,
            _read_current_temp_inner,
            subscribe=subscribe,
        )

    async def _async_read_initial(self) -> None:
        def _parse_prj2v(data: bytearray) -> None:
            prj2v = int.from_bytes(data, "little")
            self.data.prj2 = prj2v
            self.data.showing_celsius = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA == 0
            )
            self.data.display_on_cooling = bool(
                prj2v & MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING == 0
            )
            # Bit 6: the service / burn-in mode, entered by holding HEAT and AIR
            # together. It drives the device to 230 °C for ten minutes with the
            # pump off, so spec §3.6 says to surface it rather than ignore it.
            self.data.service_mode = bool(prj2v & MASK_PRJSTAT2_VOLCANO_SERVICE_MODE)
            self.data.prv2_error = bool(prj2v & MASK_PRJSTAT2_VOLCANO_ERR)

        def _parse_prj3v(data: bytearray) -> None:
            prj3v = int.from_bytes(data, "little")
            self.data.prj3 = prj3v
            self.data.vibration = bool(prj3v & MASK_PRJSTAT3_VOLCANO_VIBRATION == 0)

        def _parse_prj4v(data: bytearray) -> None:
            self.data.prj4 = int.from_bytes(data, "little")

        def _parse_prj5v(data: bytearray) -> None:
            self.data.prj5 = int.from_bytes(data, "little")

        # The fault log is ASCII *text* that spells out hex digits: a device
        # holding the entry `6161616161617261` puts those sixteen characters on
        # the wire (spec §3.5, CONFIRMED live). Hexing the bytes would encode it
        # a second time and report `36313631...` instead.
        def _parse_hist1(data: bytearray) -> None:
            self.data.hist1 = _decode_ascii(data)

        def _parse_hist2(data: bytearray) -> None:
            self.data.hist2 = _decode_ascii(data)

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

        async def _async_read_current_temp_and_subscribe() -> None:
            await self._async_read_current_temp(subscribe=True)

        await self._async_read_prj1v(subscribe=True)  # Ensure on-state is correct
        await asyncio.gather(
            _async_read_current_temp_and_subscribe(),
            _async_read_set_temp_and_subscribe(),
            self._async_read_identity_strings(),
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
            self._async_read_and_subscribe(
                SERVICE3_UUID, CHARACTERISTIC_HIST1, _parse_hist1, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE3_UUID, CHARACTERISTIC_HIST2, _parse_hist2, subscribe=False
            ),
            self._async_read_optional(
                SERVICE3_UUID, CHARACTERISTIC_PRJ4V, _parse_prj4v
            ),
            self._async_read_optional(
                SERVICE3_UUID, CHARACTERISTIC_PRJ5V, _parse_prj5v
            ),
        )
        _LOGGER.debug("Initial characteristics read complete")
        self._after_data_updated()
        self._after_device_updated()

    async def _async_read_identity_strings(self) -> None:
        """
        Read the strings that describe the device rather than its state.

        None of them changes while the device is connected, so none is
        subscribed to. The model and the mains voltage are read optionally: the
        GATT server belongs to the BLE module rather than the controller, so
        another module revision may not serve them, and neither is worth
        failing a connect over.
        """

        def _parse_serial_number(data: bytearray) -> None:
            self.data.serial_number = _decode_ascii(data)

        def _parse_model(data: bytearray) -> None:
            self.data.model = _decode_ascii(data)

        def _parse_mains_voltage(data: bytearray) -> None:
            self.data.mains_voltage = _decode_ascii(data)

        def _parse_firmware_version(data: bytearray) -> None:
            self.data.firmware_version = _decode_ascii(data)

        def _parse_firmware_ble_version(data: bytearray) -> None:
            self.data.firmware_ble_version = _decode_ascii(data)

        def _parse_bootloader_version(data: bytearray) -> None:
            self.data.bootloader_version = _decode_ascii(data)

        def _parse_firmware(data: bytearray) -> None:
            self.data.firmware = _decode_ascii(data)

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
            self._async_read_optional(
                SERVICE3_UUID, CHARACTERISTIC_MODEL, _parse_model
            ),
            self._async_read_optional(
                SERVICE3_UUID, CHARACTERISTIC_MAINS_VOLTAGE, _parse_mains_voltage
            ),
        )

    async def async_set_fan(self, on: bool) -> bool:
        """Set the fan on or off."""
        _LOGGER.debug("Setting fan to %s", on)
        # Track the write before sending it, so the device notification that
        # confirms it cannot race ahead and leave the write pending forever.
        self.data.fan_write = on
        written = await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_FAN_ON if on else CHARACTERISTIC_FAN_OFF,
            bytearray([int(on)]),
        )
        self._after_data_updated()
        return written

    async def async_set_heater(self, on: bool) -> bool:
        """Set the heater on or off."""
        _LOGGER.debug("Setting heater to %s", on)
        # Track the write before sending it, so the device notification that
        # confirms it cannot race ahead and leave the write pending forever.
        self.data.heater_write = on
        written = await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_HEATER_ON if on else CHARACTERISTIC_HEATER_OFF,
            bytearray([int(on)]),
        )
        self._after_data_updated()
        return written

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the target temperature."""
        _LOGGER.debug("Setting temperature to %s", target)
        # Track the write before sending it, so the device notification that
        # confirms it cannot race ahead and leave the write pending forever.
        self.data.set_temp_write = int(target)
        # Written as a uint32 like the vendor app does, though read as a uint16
        # (spec §2).
        written = await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_SET_TEMP,
            bytearray(int.to_bytes(int(target * 10), 4, "little")),
        )
        if written:
            await self._async_read_set_temp()
        self._after_data_updated()
        return written

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Set the toggle for showing Celsius."""
        if on:
            return await self._write_register_2(MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA)
        return await self._write_register_2(
            65536 + MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA
        )

    async def async_set_display_on_cooling(self, on: bool) -> bool:
        """Set the toggle for display on cooling."""
        if on:
            return await self._write_register_2(
                MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING
            )
        return await self._write_register_2(
            65536 + MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING
        )

    async def _write_register_2(self, mask: int) -> bool:
        """Write to register 2."""
        return await self._write_gatt(
            SERVICE3_UUID,
            CHARACTERISTIC_PRJ2V,
            bytearray(int.to_bytes(mask, 4, "little")),
        )

    async def async_set_vibration(self, on: bool) -> bool:
        """Set the toggle for vibration."""
        if on:
            return await self._write_register_3(MASK_PRJSTAT3_VOLCANO_VIBRATION)
        return await self._write_register_3(65536 + MASK_PRJSTAT3_VOLCANO_VIBRATION)

    async def _write_register_3(self, mask: int) -> bool:
        """Write to register 3."""
        return await self._write_gatt(
            SERVICE3_UUID,
            CHARACTERISTIC_PRJ3V,
            bytearray(int.to_bytes(mask, 4, "little")),
        )

    async def async_set_shut_off(self, minutes: int) -> bool:
        """Set the shut off time in minutes."""
        written = await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_SHUT_OFF,
            bytearray(int.to_bytes(minutes * 60, 2, "little")),
        )
        if written:
            self.data.shut_off = minutes
            self._after_data_updated()
        return written

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness."""
        written = await self._write_gatt(
            SERVICE_UUID,
            CHARACTERISTIC_LED_BRIGHTNESS,
            bytearray(int.to_bytes(brightness, 2, "little")),
        )
        if written:
            self.data.led_brightness = brightness
            self._after_data_updated()
        return written

    async def _async_try_ensure_written_values(self) -> None:
        """Ensure that the pending writes are written to the device."""
        await self._async_read_set_temp()
        await self._async_read_prj1v()
        if (
            self.data.fan_needs_write
            or self.data.heater_needs_write
            or self.data.set_temp_needs_write
        ) and not self.data.is_on:
            # We don't want to turn on the device after dropping commands
            self.data.clear_open_writes()

        if self.data.fan_needs_write and (fan_write := self.data.fan_write) is not None:
            await self.async_set_fan(fan_write)

        if (
            self.data.heater_needs_write
            and (heater_write := self.data.heater_write) is not None
        ):
            await self.async_set_heater(heater_write)

        if (
            self.data.set_temp_needs_write
            and (set_temp_write := self.data.set_temp_write) is not None
        ):
            await self.async_set_target_temperature(set_temp_write)


# The old name stays importable for one release, until every caller has moved
# to VolcanoDevice.
VolcanoBLE = VolcanoDevice
