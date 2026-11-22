"""Crafty / Crafty+ protocol (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .const import DeviceFamily
from .crafty_data import (
    MASK_PRJSTAT2_DISABLE_CHARGELED,
    MASK_PRJSTAT2_DISABLE_VIBRATION,
    MASK_PRJSTAT2_FIND_DEVICE,
    MASK_PRJSTAT2_PERMANENT_BLUETOOTH,
    CraftyData,
    decode_target,
)
from .device import StorzBickelDevice, UnsupportedCommandError, _decode_ascii

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

_BASE = "-4c45-4b43-4942-265a524f5453"
SERVICE_CONTROL = "00000001" + _BASE
SERVICE_IDENTITY = "00000002" + _BASE
SERVICE_STATUS = "00000003" + _BASE

# Service 1 (spec §3)
CHAR_CURRENT_TEMP = "00000011" + _BASE
CHAR_TARGET_TEMP = "00000021" + _BASE
CHAR_BOOST_TEMP = "00000031" + _BASE
CHAR_BATTERY = "00000041" + _BASE
CHAR_LED_BRIGHTNESS = "00000051" + _BASE
CHAR_AUTO_OFF_SETTING = "00000061" + _BASE
CHAR_AUTO_OFF_COUNTDOWN = "00000071" + _BASE
CHAR_HEATER_ON = "00000081" + _BASE
CHAR_HEATER_OFF = "00000091" + _BASE
# Service 2 (spec §5.1)
CHAR_FIRMWARE = "00000032" + _BASE
CHAR_SERIAL = "00000052" + _BASE
CHAR_BLE_FIRMWARE = "00000072" + _BASE
# Service 3 (spec §4)
CHAR_USE_HOURS = "00000023" + _BASE
CHAR_BATTERY_STATUS1 = "00000063" + _BASE
CHAR_BATTERY_STATUS2 = "00000073" + _BASE
CHAR_SYSTEM_STATUS = "00000083" + _BASE
CHAR_PRJSTAT1 = "00000093" + _BASE
CHAR_SECURITY_CODE = "000001b3" + _BASE
CHAR_PRJSTAT2 = "000001c3" + _BASE
CHAR_FACTORY_RESET = "000001d3" + _BASE
CHAR_USE_MINUTES = "000001e3" + _BASE
# Service 3, not used by the vendor app: only community clients read these
# (spec §4.4, SPECULATIVE). Every one is read as optional.
CHAR_CHARGER_STATUS = "000000a3" + _BASE
CHAR_BATTERY_VOLTAGE = "000000b3" + _BASE
CHAR_BATTERY_CURRENT = "000000e3" + _BASE
CHAR_BATTERY_FULL_CAPACITY = "00000143" + _BASE
CHAR_DISCHARGE_CYCLES = "00000163" + _BASE
CHAR_CHARGE_CYCLES = "00000173" + _BASE
CHAR_BATTERY_DESIGN_CAPACITY = "00000183" + _BASE
# Battery values shown as entities (spec §4.4, units STRONG on V03.25), keyed by
# the data attribute each is stored in. The first two move while charging or
# heating and are read on every fallback poll; the rest barely change and are
# read on connect and whenever the charging state flips.
BATTERY_FAST: dict[str, str] = {
    "battery_voltage": CHAR_BATTERY_VOLTAGE,
    "battery_current": CHAR_BATTERY_CURRENT,
}
BATTERY_SLOW: dict[str, str] = {
    "battery_full_capacity": CHAR_BATTERY_FULL_CAPACITY,
    "battery_design_capacity": CHAR_BATTERY_DESIGN_CAPACITY,
    "charge_cycles": CHAR_CHARGE_CYCLES,
    "discharge_cycles": CHAR_DISCHARGE_CYCLES,
}
# Read only when a diagnostics download asks for them, keyed by the name the
# diagnostics report them under. Raw uint16, undecoded on purpose.
EXTENDED_DIAGNOSTICS: dict[str, str] = {
    "battery_operating_time": "00000013" + _BASE,
    "battery_voltage": CHAR_BATTERY_VOLTAGE,
    "mains_voltage": "000000c3" + _BASE,
    "heater_voltage": "000000d3" + _BASE,
    "battery_current": CHAR_BATTERY_CURRENT,
    "pt1000_temp": "000000f3" + _BASE,
    "pt1000_temp_adjusted": "00000103" + _BASE,
    "battery_temp": "00000113" + _BASE,
    "battery_temp_min": "00000123" + _BASE,
    "battery_temp_max": "00000133" + _BASE,
    "battery_full_capacity": CHAR_BATTERY_FULL_CAPACITY,
    "battery_remaining_capacity": "00000153" + _BASE,
    "discharge_cycles": CHAR_DISCHARGE_CYCLES,
    "charge_cycles": CHAR_CHARGE_CYCLES,
    "battery_design_capacity": CHAR_BATTERY_DESIGN_CAPACITY,
    "pcb_version": "00000043" + _BASE,
}

# Spec §5.2. The factory-reset code (1000) is deliberately not defined:
# nothing here resets a device.
SECURITY_CODE_AUTO_OFF = 815
# The app writes an Int16 zero to either heater characteristic.
HEATER_PAYLOAD = bytearray(2)
SERIAL_LENGTH = 8


def _u16(data: bytearray) -> int:
    return int.from_bytes(data[:2], "little")


def _to_u16(value: int) -> bytearray:
    return bytearray(int(value).to_bytes(2, "little"))


class CraftyDevice(StorzBickelDevice):
    """A Crafty or Crafty+."""

    family = DeviceFamily.CRAFTY
    data_class = CraftyData
    data: CraftyData

    # -- reading -----------------------------------------------------------

    async def _async_read_initial(self) -> None:
        # The firmware string decides which characteristics exist (spec §6),
        # so it is read before everything that depends on it.
        await self._async_read_and_subscribe(
            SERVICE_IDENTITY, CHAR_FIRMWARE, self._parse_firmware, subscribe=False
        )
        await self._async_read_prjstat1(subscribe=True)
        reads = [
            self._async_read_and_subscribe(
                SERVICE_CONTROL,
                CHAR_CURRENT_TEMP,
                self._parse_current_temp,
                subscribe=True,
            ),
            self._async_read_target(),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_BOOST_TEMP, self._parse_boost, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_BATTERY, self._parse_battery, subscribe=True
            ),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_LED_BRIGHTNESS, self._parse_led, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_IDENTITY, CHAR_SERIAL, self._parse_serial, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_USE_HOURS, self._parse_hours, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_PRJSTAT2, self._parse_prjstat2, subscribe=True
            ),
            self._async_read_charger_status(),
            self._async_read_battery(slow=True),
        ]
        # Only firmware known to be V02.51 or newer has the settings side. A
        # string that does not parse is treated like old firmware, as the
        # commands treat it: reading the countdown (required) off a device
        # that lacks it would drop every connect.
        if self.data.is_old_firmware is False:
            reads += [
                self._async_read_optional(
                    SERVICE_CONTROL, CHAR_AUTO_OFF_SETTING, self._parse_auto_off_setting
                ),
                self._async_read_and_subscribe(
                    SERVICE_CONTROL,
                    CHAR_AUTO_OFF_COUNTDOWN,
                    self._parse_countdown,
                    subscribe=True,
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_USE_MINUTES, self._parse_minutes
                ),
                self._async_read_optional(
                    SERVICE_IDENTITY, CHAR_BLE_FIRMWARE, self._parse_ble_firmware
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_SYSTEM_STATUS, self._parse_system_status
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_BATTERY_STATUS1, self._parse_battery_status1
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_BATTERY_STATUS2, self._parse_battery_status2
                ),
            ]
        await asyncio.gather(*reads)
        _LOGGER.debug("Initial Crafty characteristics read complete")
        self._after_data_updated()
        self._after_device_updated()

    async def _async_refresh(self) -> None:
        await self._async_read_and_subscribe(
            SERVICE_CONTROL,
            CHAR_CURRENT_TEMP,
            self._parse_current_temp,
            subscribe=False,
        )
        # Not known to notify (the community clients poll it), so the
        # fallback poll is what keeps the charging state current.
        was_charging = self.data.charging
        await self._async_read_charger_status()
        await self._async_read_battery(slow=self.data.charging != was_charging)

    async def _async_read_charger_status(self) -> None:
        await self._async_read_optional(
            SERVICE_STATUS, CHAR_CHARGER_STATUS, self._parse_charger_status
        )

    async def _async_read_battery(self, *, slow: bool) -> None:
        """Read the values behind the battery entities (spec §4.4)."""
        chars = {**BATTERY_FAST, **BATTERY_SLOW} if slow else BATTERY_FAST
        for attribute, uuid in chars.items():
            await self._async_read_optional(
                SERVICE_STATUS, uuid, self._store_u16(attribute)
            )

    def _store_u16(self, attribute: str) -> Callable[[bytearray], None]:
        def _parse(data: bytearray) -> None:
            setattr(self.data, attribute, _u16(data))

        return _parse

    async def async_read_extended_diagnostics(self) -> dict[str, int | None]:
        """
        Read the community-documented service-3 values (spec §4.4).

        Only for the diagnostics download: none of them is decoded or shown as
        an entity until a device confirms what it serves. A characteristic the
        device does not serve reads None.
        """
        values: dict[str, int | None] = dict.fromkeys(EXTENDED_DIAGNOSTICS)

        def _store(name: str) -> Callable[[bytearray], None]:
            def _parse(data: bytearray) -> None:
                values[name] = _u16(data)

            return _parse

        for name, uuid in EXTENDED_DIAGNOSTICS.items():
            await self._async_read_optional(SERVICE_STATUS, uuid, _store(name))
        return values

    async def _async_read_prjstat1(self, *, subscribe: bool) -> None:
        await self._async_read_and_subscribe(
            SERVICE_STATUS, CHAR_PRJSTAT1, self._parse_prjstat1, subscribe=subscribe
        )

    async def _async_read_target(self) -> None:
        await self._async_read_and_subscribe(
            SERVICE_CONTROL, CHAR_TARGET_TEMP, self._parse_target, subscribe=False
        )

    def _parse_firmware(self, data: bytearray) -> None:
        self.data.firmware_version = _decode_ascii(data)

    def _parse_ble_firmware(self, data: bytearray) -> None:
        # Three raw bytes, shown as V1.2.3 (spec §5.1).
        self.data.firmware_ble_version = "V" + ".".join(str(b) for b in data[:3])

    def _parse_serial(self, data: bytearray) -> None:
        self.data.serial_number = _decode_ascii(data)[:SERIAL_LENGTH]

    def _parse_current_temp(self, data: bytearray) -> None:
        self.data.current_temp = round(_u16(data) / 10)

    def _parse_target(self, data: bytearray) -> None:
        self.data.set_temp = decode_target(_u16(data))

    def _parse_boost(self, data: bytearray) -> None:
        self.data.boost_temp = round(_u16(data) / 10)

    def _parse_battery(self, data: bytearray) -> None:
        self.data.battery = _u16(data)

    def _parse_led(self, data: bytearray) -> None:
        self.data.led_brightness = _u16(data)

    def _parse_auto_off_setting(self, data: bytearray) -> None:
        self.data.auto_off_seconds = _u16(data)

    async def _parse_countdown(self, data: bytearray) -> None:
        self.data.auto_off_countdown = _u16(data)
        await self._async_try_ensure_written_values()

    def _parse_hours(self, data: bytearray) -> None:
        self.data.heat_hours = _u16(data)

    def _parse_minutes(self, data: bytearray) -> None:
        self.data.heat_minutes = _u16(data)

    def _parse_prjstat1(self, data: bytearray) -> None:
        self.data.apply_prj1(_u16(data))

    def _parse_prjstat2(self, data: bytearray) -> None:
        self.data.apply_prj2(_u16(data))

    def _parse_system_status(self, data: bytearray) -> None:
        self.data.system_status = _u16(data)
        self.data.apply_status_words()

    def _parse_battery_status1(self, data: bytearray) -> None:
        self.data.battery_status1 = _u16(data)
        self.data.apply_status_words()

    def _parse_battery_status2(self, data: bytearray) -> None:
        self.data.battery_status2 = _u16(data)

    def _parse_charger_status(self, data: bytearray) -> None:
        self.data.charger_status = _u16(data)

    # -- commands ----------------------------------------------------------

    def _require_settings_firmware(self) -> None:
        """Refuse what the pre-V02.51 firmware has no characteristic for."""
        if self.data.is_old_firmware is not False:
            msg = "needs Crafty firmware V02.51 or newer"
            raise UnsupportedCommandError(msg)

    async def async_set_heater(self, on: bool) -> bool:
        """Switch the heater; PRJSTAT1 bit 4 confirms."""
        self._require_settings_firmware()
        self.data.heater_write = on
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_HEATER_ON if on else CHAR_HEATER_OFF, HEATER_PAYLOAD
        )
        self._after_data_updated()
        return written

    async def async_set_target_temperature(self, target: float) -> bool:
        """Write the target, then re-write the boost as the vendor app does."""
        self.data.set_temp_write = int(target)
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_TARGET_TEMP, _to_u16(int(target) * 10)
        )
        if written and self.data.boost_temp is not None:
            await self._write_gatt(
                SERVICE_CONTROL, CHAR_BOOST_TEMP, _to_u16(self.data.boost_temp * 10)
            )
        if written:
            await self._async_read_target()
        self._after_data_updated()
        return written

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset in °C."""
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_BOOST_TEMP, _to_u16(offset * 10)
        )
        if written:
            self.data.boost_temp = offset
            self._after_data_updated()
        return written

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness 0-100."""
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_LED_BRIGHTNESS, _to_u16(brightness)
        )
        if written:
            self.data.led_brightness = brightness
            self._after_data_updated()
        return written

    async def async_set_auto_off_seconds(self, seconds: int) -> bool:
        """Set the auto-off time; the security code unlocks the write (spec §5.2)."""
        self._require_settings_firmware()
        if not await self._write_gatt(
            SERVICE_STATUS, CHAR_SECURITY_CODE, _to_u16(SECURITY_CODE_AUTO_OFF)
        ):
            return False
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_AUTO_OFF_SETTING, _to_u16(seconds)
        )
        if written:
            self.data.auto_off_seconds = seconds
            self._after_data_updated()
        return written

    async def _async_change_prjstat2(self, mask: int, *, set_bit: bool) -> bool:
        """Read-modify-write one PRJSTAT2 bit, then re-read the word (spec §4.2)."""
        if self.data.prj2 is None:
            return False
        word = (self.data.prj2 | mask) if set_bit else (self.data.prj2 & ~mask)
        written = await self._write_gatt(SERVICE_STATUS, CHAR_PRJSTAT2, _to_u16(word))
        if written:
            await self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_PRJSTAT2, self._parse_prjstat2, subscribe=False
            )
            self._after_data_updated()
        return written

    async def async_set_vibration(self, on: bool) -> bool:
        """Bit 0 is *disable vibration*."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_DISABLE_VIBRATION, set_bit=not on
        )

    async def async_set_charge_led(self, on: bool) -> bool:
        """Bit 1 is *disable charge LED*."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_DISABLE_CHARGELED, set_bit=not on
        )

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Bit 12 keeps Bluetooth on while the device sleeps."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_PERMANENT_BLUETOOTH, set_bit=on
        )

    async def async_find_device(self) -> bool:
        """Make a Crafty+ buzz for 30 s (bit 3); the app hides this below major 3."""
        if not self.data.is_plus:
            msg = "find my device needs a Crafty+"
            raise UnsupportedCommandError(msg)
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_FIND_DEVICE, set_bit=True
        )

    # -- pending writes ----------------------------------------------------

    async def _async_try_ensure_written_values(self) -> None:
        await self._async_read_target()
        await self._async_read_prjstat1(subscribe=False)
        if (
            self.data.heater_needs_write or self.data.set_temp_needs_write
        ) and not self.data.is_on:
            # Never turn the device on by replaying a command it missed.
            self.data.clear_open_writes()
        if (
            self.data.heater_needs_write
            and (heater := self.data.heater_write) is not None
        ):
            await self.async_set_heater(heater)
        if (
            self.data.set_temp_needs_write
            and (target := self.data.set_temp_write) is not None
        ):
            await self.async_set_target_temperature(target)
