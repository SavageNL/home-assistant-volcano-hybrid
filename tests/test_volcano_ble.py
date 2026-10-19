"""Tests for the VolcanoBLE communication module."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from bleak.exc import BleakCharacteristicNotFoundError
from bleak_retry_connector import BleakNotFoundError

from custom_components.volcano_hybrid.volcano_ble.volcano_ble import (
    CHARACTERISTIC_BOOTLOADER_VERSION,
    CHARACTERISTIC_CURRENT_AUTO_OFF_TIME,
    CHARACTERISTIC_CURRENT_TEMP,
    CHARACTERISTIC_FAN_ON,
    CHARACTERISTIC_FIRMWARE,
    CHARACTERISTIC_FIRMWARE_BLE_VERSION,
    CHARACTERISTIC_FIRMWARE_VERSION,
    CHARACTERISTIC_HEAT_HOURS_CHANGED,
    CHARACTERISTIC_HEAT_MINUTES_CHANGED,
    CHARACTERISTIC_HEATER_OFF,
    CHARACTERISTIC_HEATER_ON,
    CHARACTERISTIC_HIST1,
    CHARACTERISTIC_HIST2,
    CHARACTERISTIC_LED_BRIGHTNESS,
    CHARACTERISTIC_MAINS_VOLTAGE,
    CHARACTERISTIC_MODEL,
    CHARACTERISTIC_PRJ1V,
    CHARACTERISTIC_PRJ2V,
    CHARACTERISTIC_PRJ3V,
    CHARACTERISTIC_PRJ4V,
    CHARACTERISTIC_PRJ5V,
    CHARACTERISTIC_SERIAL_NUMBER,
    CHARACTERISTIC_SET_TEMP,
    CHARACTERISTIC_SHUT_OFF,
    MASK_PRJSTAT1_VOLCANO_ACTUATOR_FAULT,
    MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA,
    MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE,
    MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING,
    MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA,
    MASK_PRJSTAT2_VOLCANO_SERVICE_MODE,
    MASK_PRJSTAT3_VOLCANO_VIBRATION,
    VolcanoBLE,
)

from . import (
    FakeVolcanoBLE,
    make_ble_device,
    make_service_info,
)
from .fakes import FakeBleakClient, FakeCharacteristic

ESTABLISH_CONNECTION = (
    "custom_components.volcano_hybrid.volcano_ble.device.establish_connection"
)


def test_is_heating_and_is_cooling_without_readings() -> None:
    """Neither derived state claims anything the device has not reported."""
    data = FakeVolcanoBLE().data

    # Nothing read yet: the heater state is unknown, so heating is too.
    assert data.is_heating is None
    assert data.is_cooling is False

    # Heater on, but no temperatures to compare yet.
    data.heater = True
    assert data.is_heating is None

    # Heater off is enough on its own: it cannot be heating.
    data.heater = False
    data.current_temp = 170
    data.set_temp = 180
    assert data.is_heating is False

    # Cooling needs a temperature to compare against, even with the display
    # set to stay on.
    data.display_on_cooling = True
    assert data.is_cooling is True
    data.current_temp = 0
    assert data.current_temp is None
    assert data.is_cooling is False


def default_values() -> dict[str, bytes]:
    """Build the characteristic values of a heating Volcano."""
    prj1v = MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA | MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE
    return {
        CHARACTERISTIC_CURRENT_TEMP: (1850).to_bytes(2, "little"),
        CHARACTERISTIC_SET_TEMP: (1900).to_bytes(2, "little"),
        CHARACTERISTIC_PRJ1V: prj1v.to_bytes(2, "little"),
        CHARACTERISTIC_PRJ2V: (0).to_bytes(2, "little"),
        CHARACTERISTIC_PRJ3V: (0).to_bytes(2, "little"),
        CHARACTERISTIC_PRJ4V: (0x1234).to_bytes(2, "little"),
        CHARACTERISTIC_PRJ5V: (0x5678).to_bytes(2, "little"),
        CHARACTERISTIC_SERIAL_NUMBER: b"VH123456 ",
        CHARACTERISTIC_MAINS_VOLTAGE: b"230VAC",
        CHARACTERISTIC_MODEL: b"HYBRID",
        CHARACTERISTIC_FIRMWARE_VERSION: b"V01.23",
        CHARACTERISTIC_FIRMWARE_BLE_VERSION: b"V01.00",
        CHARACTERISTIC_BOOTLOADER_VERSION: b"V00.90",
        CHARACTERISTIC_FIRMWARE: b"FW",
        CHARACTERISTIC_CURRENT_AUTO_OFF_TIME: (1200).to_bytes(2, "little"),
        CHARACTERISTIC_HEAT_HOURS_CHANGED: (2).to_bytes(2, "little"),
        CHARACTERISTIC_HEAT_MINUTES_CHANGED: (30).to_bytes(2, "little"),
        CHARACTERISTIC_SHUT_OFF: (1800).to_bytes(2, "little"),
        CHARACTERISTIC_LED_BRIGHTNESS: (70).to_bytes(2, "little"),
        # The fault log as a device serves it: ASCII text spelling out hex
        # digits, sixteen characters in sixteen bytes.
        CHARACTERISTIC_HIST1: b"6161616161617261",
        CHARACTERISTIC_HIST2: b"0000000000000000",
    }


async def connect(
    client: FakeBleakClient,
) -> tuple[VolcanoBLE, list[int], list[int]]:
    """Create a VolcanoBLE connected to the given fake client."""
    data_updates: list[int] = []
    device_updates: list[int] = []
    volcano = VolcanoBLE(
        lambda: data_updates.append(1), lambda: device_updates.append(1)
    )
    with patch(ESTABLISH_CONNECTION, AsyncMock(return_value=client)):
        await volcano.async_manual_update(make_ble_device())
    return volcano, data_updates, device_updates


def test_is_supported() -> None:
    """Only Volcano Hybrid devices are supported."""
    assert VolcanoBLE.is_supported(make_service_info())
    assert not VolcanoBLE.is_supported(make_service_info(manufacturer_id=76))
    assert not VolcanoBLE.is_supported(make_service_info(name="S&B CRAFTY 123"))


async def test_connect_reads_state() -> None:
    """Connecting reads the full device state."""
    client = FakeBleakClient(default_values())
    volcano, _, device_updates = await connect(client)

    assert volcano.is_connected
    data = volcano.data
    assert data.current_temp == 185
    assert data.set_temp == 190
    assert data.heater is True
    assert data.fan is True
    assert data.auto_shutdown is False
    assert data.prv1_error is False
    assert data.showing_celsius is True
    assert data.display_on_cooling is True
    assert data.prv2_error is False
    assert data.vibration is True
    assert data.serial_number == "VH123456"
    assert data.model == "HYBRID"
    assert data.mains_voltage == "230VAC"
    assert data.firmware_version == "V01.23"
    assert data.current_auto_off_time == 20.0
    assert data.heat_time == 150
    assert data.shut_off == 30
    assert data.led_brightness == 70
    assert data.connected_addr == "hci0"
    assert not data.is_assumed
    assert device_updates

    # State characteristics are subscribed to for push updates
    assert CHARACTERISTIC_CURRENT_TEMP in client.notify_callbacks
    assert CHARACTERISTIC_PRJ1V in client.notify_callbacks


async def test_connect_reads_raw_registers_and_history() -> None:
    """Connecting keeps the undecoded registers and history for diagnostics."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    data = volcano.data
    assert data.prj1 == (
        MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA | MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE
    )
    assert data.prj2 == 0
    assert data.prj3 == 0
    assert data.prj4 == 0x1234
    assert data.prj5 == 0x5678
    # The history is ASCII text, reported as the device wrote it. Hexing the
    # bytes instead would report "36313631..." — the text encoded twice.
    assert data.hist1 == "6161616161617261"
    assert data.hist2 == "0000000000000000"

    # History is read once; it is not a push characteristic
    assert CHARACTERISTIC_HIST1 not in client.notify_callbacks
    assert CHARACTERISTIC_HIST2 not in client.notify_callbacks

    # Whether the other two status words notify is unknown, so they are not
    # subscribed to either.
    assert CHARACTERISTIC_PRJ4V not in client.notify_callbacks
    assert CHARACTERISTIC_PRJ5V not in client.notify_callbacks


async def test_connect_without_the_extra_status_registers() -> None:
    """
    A device that does not serve the extra status registers still connects.

    Those two characteristics are unverified: no device has been observed
    serving them. They are read inside the same asyncio.gather as everything
    else, so a missing one must not take the connect down with it — the whole
    device would be left unusable over two diagnostic values nothing decodes.
    """
    values = default_values()
    del values[CHARACTERISTIC_PRJ4V]
    del values[CHARACTERISTIC_PRJ5V]
    client = FakeBleakClient(
        values, missing={CHARACTERISTIC_PRJ4V, CHARACTERISTIC_PRJ5V}
    )
    volcano, _, device_updates = await connect(client)

    assert volcano.is_connected
    data = volcano.data
    assert data.prj4 is None
    assert data.prj5 is None

    # Everything else came up: the values read before the missing ones in the
    # gather, the ones read after them, and the device-level callback.
    assert data.current_temp == 185
    assert data.set_temp == 190
    assert data.prj1 is not None
    assert data.serial_number == "VH123456"
    assert data.led_brightness == 70
    assert data.hist2 == "0000000000000000"
    assert device_updates
    assert CHARACTERISTIC_CURRENT_TEMP in client.notify_callbacks
    assert CHARACTERISTIC_PRJ1V in client.notify_callbacks


async def test_connect_without_the_identity_strings() -> None:
    """A device that does not serve model/mains voltage still connects."""
    values = default_values()
    del values[CHARACTERISTIC_MAINS_VOLTAGE]
    del values[CHARACTERISTIC_MODEL]
    client = FakeBleakClient(
        values, missing={CHARACTERISTIC_MAINS_VOLTAGE, CHARACTERISTIC_MODEL}
    )
    volcano, _, device_updates = await connect(client)

    assert volcano.is_connected
    data = volcano.data
    assert data.model is None
    assert data.mains_voltage is None

    # The identity the device does report is unaffected.
    assert data.serial_number == "VH123456"
    assert data.firmware_version == "V01.23"
    assert device_updates

    # Neither is subscribed to: they are fixed strings, not state.
    assert CHARACTERISTIC_MAINS_VOLTAGE not in client.notify_callbacks
    assert CHARACTERISTIC_MODEL not in client.notify_callbacks

    # And nothing writes them, even though both advertise write.
    assert client.written == []


@pytest.mark.parametrize(
    "missing",
    [
        # Read on its own before the others, to settle the on-state first.
        CHARACTERISTIC_PRJ1V,
        # Read inside the gather.
        CHARACTERISTIC_PRJ2V,
    ],
)
async def test_connect_drops_the_link_when_a_required_read_fails(
    missing: str,
) -> None:
    """
    A required characteristic that cannot be read takes the connect down.

    Keeping the link would leave the device "connected" with half its state
    unknown and some notifications never subscribed, and nothing would ever
    reconnect it to read the rest. Dropping it lets the next poll retry.
    """
    values = default_values()
    del values[missing]
    client = FakeBleakClient(values, missing={missing})
    volcano, _, device_updates = await connect(client)

    assert not volcano.is_connected
    assert volcano.client is None
    assert client.is_connected is False
    assert not device_updates
    # The device always serves it, so the table it came from is stale.
    assert client.cache_clears == 1


async def test_stale_service_table_is_discovered_afresh() -> None:
    """
    A table missing a required characteristic is not reused (issue #106).

    The device always serves the current temperature, so a table without it
    is a stale or incomplete cache. Reconnecting on that same cache would fail
    the same way on every poll until Home Assistant restarts: the cache is
    cleared, and the next connect skips it until one succeeds.
    """
    values = default_values()
    stale = FakeBleakClient(values, missing={CHARACTERISTIC_CURRENT_TEMP})
    fresh = FakeBleakClient(values)
    again = FakeBleakClient(values)
    establish = AsyncMock(side_effect=[stale, fresh, again])
    volcano = VolcanoBLE(lambda: None, lambda: None)

    with patch(ESTABLISH_CONNECTION, establish):
        await volcano.async_manual_update(make_ble_device())
        assert not volcano.is_connected
        assert stale.cache_clears == 1
        assert establish.call_args.kwargs["use_services_cache"] is True

        await volcano.async_manual_update(make_ble_device())
        assert volcano.is_connected
        assert volcano.data.current_temp == 185
        assert establish.call_args.kwargs["use_services_cache"] is False

        # Once a connect has come up, the cache is trusted again.
        await volcano.async_disconnect()
        assert fresh.cache_clears == 0
        await volcano.async_manual_update(make_ble_device())
        assert establish.call_args.kwargs["use_services_cache"] is True


async def test_refresh_on_a_stale_table_reconnects() -> None:
    """
    A refresh missing a required characteristic drops the link.

    Kept, the connection failed with "Characteristic … not found" on every
    poll and never recovered (issue #106).
    """
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)
    client.services.missing.add(CHARACTERISTIC_CURRENT_TEMP)

    await volcano.async_manual_update()

    assert not volcano.is_connected
    assert client.cache_clears == 1


async def test_write_on_a_stale_table_reconnects() -> None:
    """A command whose characteristic is missing drops the link and still fails."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)
    client.services.missing.add(CHARACTERISTIC_FAN_ON)

    with pytest.raises(BleakCharacteristicNotFoundError):
        await volcano.async_set_fan(True)

    assert not volcano.is_connected
    assert client.cache_clears == 1


async def test_optional_characteristics_do_not_mark_the_table_stale() -> None:
    """A characteristic not every device serves is absent, not a stale cache."""
    values = default_values()
    del values[CHARACTERISTIC_PRJ4V]
    client = FakeBleakClient(values, missing={CHARACTERISTIC_PRJ4V})
    volcano, _, _ = await connect(client)

    await volcano.async_disconnect()

    assert client.cache_clears == 0


async def test_failing_optional_read_does_not_drop_the_link() -> None:
    """An optional characteristic that is served but cannot be read is skipped."""

    class FailingReadClient(FakeBleakClient):
        async def read_gatt_char(self, char: FakeCharacteristic) -> bytearray:
            if char.uuid == CHARACTERISTIC_PRJ5V:
                raise BleakError
            return await super().read_gatt_char(char)

    client = FailingReadClient(default_values())
    volcano, _, _ = await connect(client)

    assert volcano.is_connected
    assert volcano.data.prj5 is None
    assert volcano.data.prj4 == 0x1234


async def test_failing_cache_clear_still_disconnects() -> None:
    """Clearing the cache is best effort; the next connect skips it anyway."""

    class NoClearClient(FakeBleakClient):
        async def clear_cache(self) -> bool:
            raise BleakError

    values = default_values()
    del values[CHARACTERISTIC_PRJ1V]
    client = NoClearClient(values, missing={CHARACTERISTIC_PRJ1V})
    volcano, _, _ = await connect(client)

    assert not volcano.is_connected
    assert client.is_connected is False


async def test_connect_drops_the_link_when_a_read_times_out() -> None:
    """A read that times out (over a proxy, say) is handled like a failed one."""

    class TimingOutClient(FakeBleakClient):
        async def read_gatt_char(self, char: FakeCharacteristic) -> bytearray:
            if char.uuid == CHARACTERISTIC_PRJ3V:
                raise TimeoutError
            return await super().read_gatt_char(char)

    client = TimingOutClient(default_values())
    volcano, _, device_updates = await connect(client)

    assert not volcano.is_connected
    assert client.is_connected is False
    assert not device_updates


async def test_undecodable_text_falls_back_to_hex() -> None:
    """
    Bytes that are not ASCII are reported as hex instead of raising.

    The parsing runs inside the initial read, so an exception there would abort
    the connect entirely — over a diagnostic string.
    """
    values = default_values()
    values[CHARACTERISTIC_HIST1] = bytes.fromhex("00ff11223344556677")
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    assert volcano.is_connected
    assert volcano.data.hist1 == "00ff11223344556677"
    # The characteristics that did decode are unaffected.
    assert volcano.data.hist2 == "0000000000000000"


async def test_prj1_notification_updates_raw_register() -> None:
    """A status notification refreshes the raw register, not just the flags."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    callback = client.notify_callbacks[CHARACTERISTIC_PRJ1V]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_PRJ1V),
        bytearray((MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA).to_bytes(2, "little")),
    )

    assert volcano.data.prj1 == MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA
    assert volcano.data.fan is False


async def test_prj1_decodes_temperature_reached_and_actuator_fault() -> None:
    """
    The status register carries the device's own "setpoint reached" signal.

    Observed live: heating below the setpoint reports 0x0023 and reaching it
    reports 0x0623, so bits 9 (auto shutdown) and 10 (reached) flip together
    at the setpoint, not at heat start.
    """
    values = default_values()
    values[CHARACTERISTIC_PRJ1V] = (0x0023).to_bytes(2, "little")
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    assert volcano.data.heater is True
    assert volcano.data.at_temperature is False
    assert volcano.data.auto_shutdown is False
    assert volcano.data.actuator_fault is False

    callback = client.notify_callbacks[CHARACTERISTIC_PRJ1V]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_PRJ1V),
        bytearray((0x0623).to_bytes(2, "little")),
    )

    assert volcano.data.at_temperature is True
    assert volcano.data.auto_shutdown is True

    # Bit 4 is the heater/pump feedback fault; it is part of the ERR mask too.
    await callback(
        FakeCharacteristic(CHARACTERISTIC_PRJ1V),
        bytearray(
            (0x0623 | MASK_PRJSTAT1_VOLCANO_ACTUATOR_FAULT).to_bytes(2, "little")
        ),
    )

    assert volcano.data.actuator_fault is True
    assert volcano.data.prv1_error is True


async def test_status_register_decodes_service_mode() -> None:
    """The service-mode bit is decoded, not written."""
    values = default_values()
    values[CHARACTERISTIC_PRJ2V] = MASK_PRJSTAT2_VOLCANO_SERVICE_MODE.to_bytes(
        2, "little"
    )
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    data = volcano.data
    assert data.service_mode is True
    # Burn-in is a mode, not an error condition.
    assert data.prv2_error is False

    # And it follows the device back down again.
    callback = client.notify_callbacks[CHARACTERISTIC_PRJ2V]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_PRJ2V),
        bytearray((0).to_bytes(2, "little")),
    )

    assert data.service_mode is False


async def test_notifications_update_data() -> None:
    """Device notifications update the data and notify the listener."""
    client = FakeBleakClient(default_values())
    volcano, data_updates, _ = await connect(client)
    data_updates.clear()

    callback = client.notify_callbacks[CHARACTERISTIC_CURRENT_TEMP]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_CURRENT_TEMP),
        bytearray((2000).to_bytes(2, "little")),
    )

    assert volcano.data.current_temp == 200
    assert data_updates


@pytest.mark.parametrize("raw", [0xFFFF, 65360, 2310])
async def test_out_of_range_current_temperature_is_no_reading(raw: int) -> None:
    """
    A reading above 230 °C is no reading, including the vendor's sentinel.

    The vendor app ignores a value that rounds to 6536 °C or more (0xFFFF);
    anything above the 230 °C maximum is already treated as unknown here.
    """
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    callback = client.notify_callbacks[CHARACTERISTIC_CURRENT_TEMP]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_CURRENT_TEMP),
        bytearray(raw.to_bytes(2, "little")),
    )

    assert volcano.data.current_temp is None


async def test_set_fan_and_heater() -> None:
    """Fan and heater commands write the matching characteristics."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    assert await volcano.async_set_fan(True)
    assert (CHARACTERISTIC_FAN_ON, b"\x01") in client.written

    assert await volcano.async_set_heater(False)
    assert (CHARACTERISTIC_HEATER_OFF, b"\x00") in client.written


async def test_set_target_temperature() -> None:
    """The target temperature is written and read back."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    client.values[CHARACTERISTIC_SET_TEMP] = (1950).to_bytes(2, "little")
    assert await volcano.async_set_target_temperature(195)

    assert (CHARACTERISTIC_SET_TEMP, (1950).to_bytes(4, "little")) in client.written
    assert volcano.data.set_temp == 195
    assert volcano.data.set_temp_state == 195
    assert not volcano.data.is_assumed


async def test_settings_writes() -> None:
    """Setting writes use the documented encodings."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)

    assert await volcano.async_set_shut_off(45)
    assert (CHARACTERISTIC_SHUT_OFF, (2700).to_bytes(2, "little")) in client.written
    assert volcano.data.shut_off == 45

    assert await volcano.async_set_led_brightness(80)
    assert (CHARACTERISTIC_LED_BRIGHTNESS, (80).to_bytes(2, "little")) in client.written
    assert volcano.data.led_brightness == 80

    assert await volcano.async_set_showing_celsius(True)
    assert (
        CHARACTERISTIC_PRJ2V,
        MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA.to_bytes(4, "little"),
    ) in client.written

    assert await volcano.async_set_showing_celsius(False)
    assert (
        CHARACTERISTIC_PRJ2V,
        (65536 + MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA).to_bytes(4, "little"),
    ) in client.written

    assert await volcano.async_set_display_on_cooling(True)
    assert (
        CHARACTERISTIC_PRJ2V,
        MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING.to_bytes(4, "little"),
    ) in client.written

    assert await volcano.async_set_vibration(False)
    assert (
        CHARACTERISTIC_PRJ3V,
        (65536 + MASK_PRJSTAT3_VOLCANO_VIBRATION).to_bytes(4, "little"),
    ) in client.written


async def test_pending_writes_dropped_when_device_off() -> None:
    """Pending writes are dropped instead of turning on the device."""
    values = default_values()
    values[CHARACTERISTIC_PRJ1V] = (0).to_bytes(2, "little")  # device off
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    volcano.data.fan_write = True
    assert volcano.device is not None
    await volcano.async_manual_update(volcano.device)

    assert volcano.data.fan_write is None
    assert not any(uuid == CHARACTERISTIC_FAN_ON for uuid, _ in client.written)


async def test_pending_writes_replayed_when_device_on() -> None:
    """Pending writes are replayed while the device is on."""
    values = default_values()
    # Fan on, heater off
    values[CHARACTERISTIC_PRJ1V] = MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE.to_bytes(
        2, "little"
    )
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    volcano.data.heater_write = True
    assert volcano.device is not None
    await volcano.async_manual_update(volcano.device)

    assert (CHARACTERISTIC_HEATER_ON, b"\x01") in client.written


async def test_update_rereads_current_temperature() -> None:
    """
    The periodic update re-reads the current temperature.

    Regression test: the current temperature was only read once, at connect,
    and then left to the notification subscription. Notifications are
    unacknowledged, and the device only notifies on change, so a single
    dropped packet froze the reading in Home Assistant indefinitely.
    """
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)
    assert volcano.data.current_temp == 185

    # The device heats up but the notification never arrives.
    client.values[CHARACTERISTIC_CURRENT_TEMP] = (1900).to_bytes(2, "little")

    assert volcano.device is not None
    await volcano.async_manual_update(volcano.device)

    assert volcano.data.current_temp == 190


async def test_pending_write_during_connect_does_not_deadlock() -> None:
    """
    A pending write is replayed during the initial connect without hanging.

    Regression test: the auto-off-time characteristic replays pending writes
    from its callback, which the initial read invokes while the connect still
    holds the connection lock. Re-acquiring that lock for the write deadlocked
    the connect, wedging the coordinator until Home Assistant restarted.
    """
    client = FakeBleakClient(default_values())  # device on, set_temp 190
    volcano = VolcanoBLE(lambda: None, lambda: None)

    # A command issued while disconnected leaves a write pending.
    volcano.data.set_temp_write = 200

    with patch(ESTABLISH_CONNECTION, AsyncMock(return_value=client)):
        async with asyncio.timeout(5):
            await volcano.async_manual_update(make_ble_device())

    assert volcano.is_connected
    assert (CHARACTERISTIC_SET_TEMP, (2000).to_bytes(4, "little")) in client.written


class ConfirmingClient(FakeBleakClient):
    """
    A client that confirms heater writes before the write call returns.

    Real devices push the prj1v status notification as soon as the heater
    toggles, which can arrive before the write acknowledgement.
    """

    async def write_gatt_char(self, char: FakeCharacteristic, value: bytearray) -> None:
        """Record a write and confirm heater changes via notification."""
        await super().write_gatt_char(char, value)
        if char.uuid in (CHARACTERISTIC_HEATER_ON, CHARACTERISTIC_HEATER_OFF):
            prj1v = MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE
            if char.uuid == CHARACTERISTIC_HEATER_ON:
                prj1v |= MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA
            await self.notify(CHARACTERISTIC_PRJ1V, prj1v.to_bytes(2, "little"))

    async def notify(self, characteristic: str, value: bytes) -> None:
        """Push a notification for a characteristic, updating its value."""
        self.values[characteristic] = value
        await self.notify_callbacks[characteristic](
            FakeCharacteristic(characteristic), bytearray(value)
        )


async def test_physical_turn_on_is_not_reverted() -> None:
    """
    Turning the device on at the device is not undone by an old command.

    Regression test: the off command was confirmed by a notification before
    the write tracking was recorded, leaving a pending "heater off" write
    that was replayed when the user later turned the device on physically.
    """
    client = ConfirmingClient(default_values())  # heater and fan on
    volcano, _, _ = await connect(client)

    # The user turns the heater off through Home Assistant
    assert await volcano.async_set_heater(False)
    assert volcano.data.heater is False
    assert not volcano.data.heater_needs_write

    # The user turns the heater back on with the button on the device
    prj1v_on = (
        MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA | MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE
    )
    await client.notify(CHARACTERISTIC_PRJ1V, prj1v_on.to_bytes(2, "little"))
    assert volcano.data.heater is True

    # The next update cycle must not replay the old off command
    client.written.clear()
    assert volcano.device is not None
    await volcano.async_manual_update(volcano.device)

    assert (CHARACTERISTIC_HEATER_OFF, b"\x00") not in client.written
    assert volcano.data.heater_state is True


async def test_write_fails_without_device() -> None:
    """Commands report failure when there is no device to connect to."""
    volcano = VolcanoBLE(lambda: None, lambda: None)
    assert not await volcano.async_set_fan(True)


async def test_connect_failure() -> None:
    """A connection failure leaves the device disconnected."""
    volcano = VolcanoBLE(lambda: None, lambda: None)
    with patch(ESTABLISH_CONNECTION, AsyncMock(side_effect=BleakNotFoundError("gone"))):
        await volcano.async_manual_update(make_ble_device())

    assert not volcano.is_connected


async def test_disconnect_callback() -> None:
    """The bleak disconnect callback marks the device disconnected."""
    client = FakeBleakClient(default_values())
    data_updates: list[int] = []
    volcano = VolcanoBLE(lambda: data_updates.append(1), lambda: None)
    with patch(ESTABLISH_CONNECTION, AsyncMock(return_value=client)) as establish_mock:
        await volcano.async_manual_update(make_ble_device())

    assert volcano.is_connected
    data_updates.clear()

    disconnected_callback = establish_mock.call_args.kwargs["disconnected_callback"]
    disconnected_callback(client)

    assert not volcano.is_connected
    assert data_updates


async def test_rssi_updates_notify() -> None:
    """Updating the rssi notifies the listener once per change."""
    data_updates: list[int] = []
    volcano = VolcanoBLE(lambda: data_updates.append(1), lambda: None)

    volcano.rssi = -50
    assert volcano.data.rssi == -50
    assert len(data_updates) == 1

    volcano.rssi = -50
    assert len(data_updates) == 1


async def test_concurrent_updates_establish_single_connection() -> None:
    """A burst of concurrent updates only opens one client (no leaked slots)."""
    device = make_ble_device()
    volcano = VolcanoBLE(lambda: None, lambda: None, device=device)

    async def _establish(*_args: Any, **_kwargs: Any) -> FakeBleakClient:
        # Yield so every concurrent attempt reaches the connection lock before
        # the first one finishes connecting.
        await asyncio.sleep(0)
        return FakeBleakClient(default_values())

    with patch(ESTABLISH_CONNECTION, side_effect=_establish) as establish_mock:
        await asyncio.gather(*(volcano.async_manual_update(device) for _ in range(5)))

    assert volcano.is_connected
    assert establish_mock.call_count == 1


@pytest.mark.parametrize("explicit_disconnect", [True, False])
async def test_explicit_disconnect(explicit_disconnect: bool) -> None:
    """Disconnecting tears down the client."""
    client = FakeBleakClient(default_values())
    volcano, _, _ = await connect(client)
    assert volcano.is_connected

    if explicit_disconnect:
        await volcano.async_disconnect()
    else:
        client.is_connected = False

    assert not volcano.is_connected


class DroppingClient(FakeBleakClient):
    """A client whose link drops while the auto-off time is read."""

    def __init__(self, values: dict[str, bytes]) -> None:
        """Initialize, with nobody to tell about the drop yet."""
        super().__init__(values)
        self.on_drop: list[Any] = []

    async def read_gatt_char(self, char: FakeCharacteristic) -> bytearray:
        """Serve the value, dropping the link on the auto-off time."""
        value = await super().read_gatt_char(char)
        if char.uuid == CHARACTERISTIC_CURRENT_AUTO_OFF_TIME and self.is_connected:
            self.is_connected = False
            for callback in self.on_drop:
                callback(self)
        return value


async def test_link_drop_during_connect_replay_does_not_deadlock() -> None:
    """
    A pending write replayed during a connect whose link drops does not hang.

    Regression test: the auto-off-time callback replays pending writes while
    the connect holds the connection lock. With the link already gone, the
    replayed write tried to connect again and waited for that same lock.
    """
    first = DroppingClient(default_values())  # device on, set_temp 190
    second = FakeBleakClient(default_values())
    volcano = VolcanoBLE(lambda: None, lambda: None)
    first.on_drop.append(volcano._disconnected)  # noqa: SLF001
    volcano.data.set_temp_write = 200

    with patch(ESTABLISH_CONNECTION, AsyncMock(side_effect=[first, second])):
        async with asyncio.timeout(5):
            await volcano.async_manual_update(make_ble_device())

    assert not volcano._connect_lock.locked()  # noqa: SLF001
    # The update reconnected afterwards and delivered the write it held.
    assert volcano.client is second
    assert volcano.is_connected
    assert (CHARACTERISTIC_SET_TEMP, (2000).to_bytes(4, "little")) in second.written
