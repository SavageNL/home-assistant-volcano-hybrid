"""Tests for the Crafty protocol against a fake GATT server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bleak_retry_connector import BleakNotFoundError

from custom_components.volcano_hybrid.volcano_ble.crafty import (
    CHAR_AUTO_OFF_COUNTDOWN,
    CHAR_AUTO_OFF_SETTING,
    CHAR_BATTERY,
    CHAR_BATTERY_CURRENT,
    CHAR_BATTERY_DESIGN_CAPACITY,
    CHAR_BATTERY_FULL_CAPACITY,
    CHAR_BATTERY_STATUS1,
    CHAR_BATTERY_STATUS2,
    CHAR_BATTERY_VOLTAGE,
    CHAR_BLE_FIRMWARE,
    CHAR_BOOST_TEMP,
    CHAR_CHARGE_CYCLES,
    CHAR_CHARGER_STATUS,
    CHAR_CURRENT_TEMP,
    CHAR_DISCHARGE_CYCLES,
    CHAR_FACTORY_RESET,
    CHAR_FIRMWARE,
    CHAR_HEATER_OFF,
    CHAR_HEATER_ON,
    CHAR_LED_BRIGHTNESS,
    CHAR_PRJSTAT1,
    CHAR_PRJSTAT2,
    CHAR_SECURITY_CODE,
    CHAR_SERIAL,
    CHAR_SYSTEM_STATUS,
    CHAR_TARGET_TEMP,
    CHAR_USE_HOURS,
    CHAR_USE_MINUTES,
    EXTENDED_DIAGNOSTICS,
    SECURITY_CODE_AUTO_OFF,
    CraftyDevice,
)
from custom_components.volcano_hybrid.volcano_ble.crafty_data import (
    MASK_PRJSTAT2_SET_TEMP_REACHED,
    MASK_PRJSTAT_CRAFTY_ACTIVE,
)
from custom_components.volcano_hybrid.volcano_ble.device import UnsupportedCommandError

from . import make_ble_device
from .fakes import FakeBleakClient

ESTABLISH = "custom_components.volcano_hybrid.volcano_ble.device.establish_connection"

# Characteristics only served from firmware V02.51 on (spec §3, §4, §5.1).
SETTINGS_CHARS = {
    CHAR_AUTO_OFF_SETTING,
    CHAR_AUTO_OFF_COUNTDOWN,
    CHAR_HEATER_ON,
    CHAR_HEATER_OFF,
    CHAR_USE_MINUTES,
    CHAR_BLE_FIRMWARE,
    CHAR_SECURITY_CODE,
    CHAR_FACTORY_RESET,
    CHAR_SYSTEM_STATUS,
    CHAR_BATTERY_STATUS1,
    CHAR_BATTERY_STATUS2,
}


def u16(value: int) -> bytes:
    """Encode a uint16 the way the device serves it."""
    return value.to_bytes(2, "little")


def crafty_plus_values() -> dict[str, bytes]:
    """Build the characteristic values of a heating Crafty+ on V03.02."""
    return {
        CHAR_CURRENT_TEMP: u16(1830),
        CHAR_TARGET_TEMP: u16(1850),
        CHAR_BOOST_TEMP: u16(150),
        CHAR_BATTERY: u16(85),
        CHAR_LED_BRIGHTNESS: u16(70),
        CHAR_AUTO_OFF_SETTING: u16(120),
        CHAR_AUTO_OFF_COUNTDOWN: u16(90),
        CHAR_SERIAL: b"CY123456XYZ",
        CHAR_FIRMWARE: b"V03.02",
        CHAR_BLE_FIRMWARE: bytes([1, 2, 3]),
        CHAR_USE_HOURS: u16(12),
        CHAR_USE_MINUTES: u16(34),
        CHAR_PRJSTAT1: u16(MASK_PRJSTAT_CRAFTY_ACTIVE),
        CHAR_PRJSTAT2: u16(MASK_PRJSTAT2_SET_TEMP_REACHED | 0x1000),
        CHAR_SYSTEM_STATUS: u16(0),
        CHAR_BATTERY_STATUS1: u16(0),
        CHAR_BATTERY_STATUS2: u16(0),
        CHAR_CHARGER_STATUS: u16(2),
        # The charging snapshot from a real Crafty+ (spec §9.2).
        CHAR_BATTERY_VOLTAGE: u16(4184),
        CHAR_BATTERY_CURRENT: u16(757),
        CHAR_BATTERY_FULL_CAPACITY: u16(3300),
        CHAR_BATTERY_DESIGN_CAPACITY: u16(3300),
        CHAR_CHARGE_CYCLES: u16(565),
        CHAR_DISCHARGE_CYCLES: u16(195),
    }


async def connect(client: FakeBleakClient) -> CraftyDevice:
    """Create a CraftyDevice connected to the given fake client."""
    device = CraftyDevice(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)):
        await device.async_manual_update(make_ble_device(name="STORZ&BICKEL"))
    return device


async def test_connect_reads_a_crafty_plus() -> None:
    """Everything the spec lists is read, and the push characteristics subscribed."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    data = device.data

    assert device.is_connected
    assert data.model_name == "Crafty+"
    assert data.current_temp == 183
    assert data.set_temp == 185
    assert data.boost_temp == 15
    assert data.battery == 85
    assert data.led_brightness == 70
    assert data.auto_off_seconds == 120
    assert data.auto_off_countdown == 90
    assert data.serial_number == "CY123456"
    assert data.firmware_version == "V03.02"
    assert data.firmware_ble_version == "V1.2.3"
    assert data.heat_time == 12 * 60 + 34
    assert data.heater is True
    assert data.at_temperature is True
    assert data.permanent_bluetooth is True
    assert data.error is False
    assert data.charger_status == 2
    assert data.charging is True
    for uuid in (
        CHAR_CURRENT_TEMP,
        CHAR_BATTERY,
        CHAR_AUTO_OFF_COUNTDOWN,
        CHAR_PRJSTAT1,
        CHAR_PRJSTAT2,
    ):
        assert uuid in client.notify_callbacks
    assert CHAR_TARGET_TEMP not in client.notify_callbacks


async def test_target_in_fahrenheit_is_converted() -> None:
    """A device set to °F reports °F x10; it is read as °C (spec §3.1)."""
    values = crafty_plus_values()
    values[CHAR_TARGET_TEMP] = u16(3650)
    device = await connect(FakeBleakClient(values))
    assert device.data.set_temp == 185


async def test_old_firmware_skips_the_settings_characteristics() -> None:
    """Below V02.51 the settings side is not read and the heater cannot be switched."""
    values = {k: v for k, v in crafty_plus_values().items() if k not in SETTINGS_CHARS}
    values[CHAR_FIRMWARE] = b"V02.49"
    client = FakeBleakClient(values, missing=SETTINGS_CHARS)
    device = await connect(client)

    assert device.is_connected
    assert device.data.is_old_firmware is True
    assert device.data.model_name == "Crafty"
    assert device.data.heat_time == 12 * 60
    assert device.data.auto_off_seconds is None
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_heater(True)
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_auto_off_seconds(200)
    assert client.written == []


async def test_unparseable_firmware_is_treated_like_old_firmware() -> None:
    """
    A firmware string that says nothing about the generation reads nothing extra.

    Regression test: unknown firmware was read as new, so the settings side
    was read too, and a device that did not serve the (required) auto-off
    countdown dropped every connect and reconnected in a loop. The commands
    already refused unknown firmware; the reads now agree with them.
    """
    values = {k: v for k, v in crafty_plus_values().items() if k not in SETTINGS_CHARS}
    values[CHAR_FIRMWARE] = b"garbage"
    client = FakeBleakClient(values, missing=SETTINGS_CHARS)
    device = await connect(client)

    assert device.is_connected
    assert device.data.is_old_firmware is None
    assert device.data.auto_off_seconds is None
    assert device.data.auto_off_countdown is None
    assert device.data.system_status is None
    assert device.data.current_temp == 183
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_heater(True)


async def test_a_missing_required_characteristic_drops_the_link() -> None:
    """Unlike the optional settings side, a missing current temperature fails."""
    values = crafty_plus_values()
    del values[CHAR_CURRENT_TEMP]
    client = FakeBleakClient(values, missing={CHAR_CURRENT_TEMP})
    device = await connect(client)

    assert not device.is_connected
    assert device.client is None
    assert client.is_connected is False


async def test_heater_writes_two_zero_bytes_and_tracks_the_write() -> None:
    """Heater on/off are separate characteristics written with `00 00` (spec §3)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_heater(False)
    assert client.written == [(CHAR_HEATER_OFF, b"\x00\x00")]
    assert device.data.heater_write is False
    assert device.data.is_assumed

    # The device confirms through PRJSTAT1.
    await client.notify_callbacks[CHAR_PRJSTAT1](None, bytearray(u16(0)))
    assert device.data.heater is False
    assert not device.data.is_assumed

    assert await device.async_set_heater(True)
    assert client.written[-1] == (CHAR_HEATER_ON, b"\x00\x00")


async def test_target_write_rewrites_the_boost() -> None:
    """Writing the target is followed by re-writing the boost (spec §3.2)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_target_temperature(190)
    assert client.written == [
        (CHAR_TARGET_TEMP, u16(1900)),
        (CHAR_BOOST_TEMP, u16(150)),
    ]
    assert device.data.set_temp_write == 190


async def test_auto_off_write_is_preceded_by_the_security_code() -> None:
    """The auto-off setting needs code 815 written first (spec §5.2)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_auto_off_seconds(200)
    assert client.written == [
        (CHAR_SECURITY_CODE, u16(SECURITY_CODE_AUTO_OFF)),
        (CHAR_AUTO_OFF_SETTING, u16(200)),
    ]
    assert device.data.auto_off_seconds == 200


async def test_prjstat2_settings_are_read_modify_write() -> None:
    """A settings bit is flipped in the whole word and the word re-read (spec §4.2)."""
    values = crafty_plus_values()
    client = FakeBleakClient(values)
    device = await connect(client)
    client.written.clear()
    values[CHAR_PRJSTAT2] = u16(0x1004 | 0x0001)

    assert await device.async_set_vibration(False)
    assert client.written == [(CHAR_PRJSTAT2, u16(0x1004 | 0x0001))]
    assert device.data.vibration is False

    client.written.clear()
    values[CHAR_PRJSTAT2] = u16(0x0004 | 0x0001)
    assert await device.async_set_permanent_bluetooth(False)
    assert client.written == [(CHAR_PRJSTAT2, u16(0x0004 | 0x0001))]
    assert device.data.permanent_bluetooth is False


async def test_find_device_needs_a_crafty_plus() -> None:
    """Find-my-Crafty sets PRJSTAT2 bit 3; the original Crafty has no such mode."""
    values = crafty_plus_values()
    client = FakeBleakClient(values)
    device = await connect(client)
    client.written.clear()
    assert await device.async_find_device()
    assert client.written == [(CHAR_PRJSTAT2, u16(0x1004 | 0x0008))]

    values[CHAR_FIRMWARE] = b"V02.60"
    device = await connect(FakeBleakClient(values))
    with pytest.raises(UnsupportedCommandError):
        await device.async_find_device()


async def test_pending_writes_are_dropped_when_the_device_is_off() -> None:
    """A queued write never turns a switched-off Crafty on (VOLCANO_BLE_SPEC.md §5)."""
    values = crafty_plus_values()
    values[CHAR_PRJSTAT1] = u16(0)
    client = FakeBleakClient(values)
    device = await connect(client)
    device.data.set_temp_write = 200
    await device.async_manual_update()
    assert device.data.set_temp_write is None
    assert (CHAR_TARGET_TEMP, u16(2000)) not in client.written


async def test_simple_settings_are_written_as_uint16() -> None:
    """Boost (x10), LED brightness and the charge LED bit are plain writes."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_boost_temperature(20)
    assert await device.async_set_led_brightness(40)
    assert await device.async_set_charge_led(False)
    assert client.written == [
        (CHAR_BOOST_TEMP, u16(200)),
        (CHAR_LED_BRIGHTNESS, u16(40)),
        (CHAR_PRJSTAT2, u16(0x1004 | 0x0002)),
    ]
    assert device.data.boost_temp == 20
    assert device.data.led_brightness == 40


async def test_nothing_is_written_while_disconnected() -> None:
    """Without a connection no command reports success."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    await device.async_disconnect()
    client.written.clear()

    with patch(ESTABLISH, AsyncMock(side_effect=BleakNotFoundError("gone"))):
        assert not await device.async_set_target_temperature(190)
        assert not await device.async_set_auto_off_seconds(200)
        assert not await device.async_set_boost_temperature(20)
        assert not await device.async_set_led_brightness(40)
        assert not await device.async_set_vibration(False)
    assert client.written == []


async def test_unconfirmed_writes_are_replayed_while_on() -> None:
    """A countdown notification re-sends what the device has not confirmed."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    assert await device.async_set_heater(False)
    assert await device.async_set_target_temperature(190)
    client.written.clear()

    await client.notify_callbacks[CHAR_AUTO_OFF_COUNTDOWN](None, bytearray(u16(80)))
    assert device.data.auto_off_countdown == 80
    assert client.written == [
        (CHAR_HEATER_OFF, b"\x00\x00"),
        (CHAR_TARGET_TEMP, u16(1900)),
        (CHAR_BOOST_TEMP, u16(150)),
    ]


async def test_charger_status_is_optional_and_polled() -> None:
    """A device without 000000a3 still connects; one with it is re-read on refresh."""
    values = crafty_plus_values()
    del values[CHAR_CHARGER_STATUS]
    device = await connect(FakeBleakClient(values, missing={CHAR_CHARGER_STATUS}))
    assert device.is_connected
    assert device.data.charging is None

    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    assert device.data.charging is True
    assert CHAR_CHARGER_STATUS not in client.notify_callbacks
    client.values[CHAR_CHARGER_STATUS] = u16(0)
    await device.async_manual_update()
    assert device.data.charging is False


async def test_extended_diagnostics_are_read_on_demand() -> None:
    """Served values are read raw on request; the rest read None."""
    values = crafty_plus_values()
    values[EXTENDED_DIAGNOSTICS["battery_voltage"]] = u16(4012)
    values[EXTENDED_DIAGNOSTICS["charge_cycles"]] = u16(57)
    served = {
        EXTENDED_DIAGNOSTICS["battery_voltage"],
        EXTENDED_DIAGNOSTICS["charge_cycles"],
    }
    missing = set(EXTENDED_DIAGNOSTICS.values()) - served
    device = await connect(FakeBleakClient(values, missing=missing))
    assert device.data.battery_voltage == 4012

    extended = await device.async_read_extended_diagnostics()

    assert set(extended) == set(EXTENDED_DIAGNOSTICS)
    assert extended["battery_voltage"] == 4012
    assert extended["charge_cycles"] == 57
    assert extended["mains_voltage"] is None


async def test_extended_diagnostics_while_disconnected() -> None:
    """Without a link every value reads None instead of failing the download."""
    device = CraftyDevice(lambda: None, lambda: None)
    extended = await device.async_read_extended_diagnostics()
    assert set(extended.values()) == {None}


async def test_battery_values_are_read_and_polled() -> None:
    """Voltage and current follow every poll; the rest only a charging change."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    data = device.data
    assert (data.battery_voltage, data.battery_current) == (4184, 757)
    assert (data.charge_cycles, data.discharge_cycles) == (565, 195)
    assert data.battery_health == 100

    # Still charging: only the fast values are read again.
    client.values[CHAR_BATTERY_VOLTAGE] = u16(4190)
    client.values[CHAR_BATTERY_CURRENT] = u16(700)
    client.values[CHAR_CHARGE_CYCLES] = u16(566)
    await device.async_manual_update()
    assert (data.battery_voltage, data.battery_current) == (4190, 700)
    assert data.charge_cycles == 565

    # Unplugged: the charging state flips, so the slow values follow.
    client.values[CHAR_CHARGER_STATUS] = u16(0)
    client.values[CHAR_BATTERY_FULL_CAPACITY] = u16(2970)
    await device.async_manual_update()
    assert data.charging is False
    assert data.charge_cycles == 566
    assert data.battery_health == 90


async def test_battery_values_are_optional() -> None:
    """A device that serves none of them still connects, with no values."""
    chars = {
        CHAR_BATTERY_VOLTAGE,
        CHAR_BATTERY_CURRENT,
        CHAR_BATTERY_FULL_CAPACITY,
        CHAR_BATTERY_DESIGN_CAPACITY,
        CHAR_CHARGE_CYCLES,
        CHAR_DISCHARGE_CYCLES,
    }
    values = {k: v for k, v in crafty_plus_values().items() if k not in chars}
    device = await connect(FakeBleakClient(values, missing=chars))
    assert device.is_connected
    assert device.data.battery_voltage is None
    assert device.data.battery_health is None
