"""Tests for the VolcanoBLE communication module."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
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
    MASK_PRJSTAT1_VOLCANO_AIR_STEP_MODE,
    MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA,
    MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE,
    MASK_PRJSTAT1_VOLCANO_SECOND_STAGE,
    MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING,
    MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA,
    MASK_PRJSTAT2_VOLCANO_SERVICE_MODE,
    MASK_PRJSTAT3_VOLCANO_VIBRATION,
    VolcanoBLE,
)

from . import (
    VOLCANO_ADDRESS,
    FakeVolcanoBLE,
    make_ble_device,
    make_service_info,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ESTABLISH_CONNECTION = (
    "custom_components.volcano_hybrid.volcano_ble.volcano_ble.establish_connection"
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


class FakeCharacteristic:
    """A GATT characteristic that only knows its uuid."""

    def __init__(self, uuid: str) -> None:
        """Initialize the characteristic."""
        self.uuid = uuid


class FakeService:
    """A GATT service handing out characteristics."""

    def __init__(self, missing: set[str]) -> None:
        """Initialize the service."""
        self.missing = missing

    def get_characteristic(self, uuid: str) -> FakeCharacteristic | None:
        """Get a characteristic by uuid, returning None when the device lacks it."""
        return None if uuid in self.missing else FakeCharacteristic(uuid)


class FakeServices:
    """A GATT service collection."""

    def __init__(self, missing: set[str]) -> None:
        """Initialize the collection."""
        self.missing = missing

    def get_service(self, uuid: str) -> FakeService:
        """Get a service by uuid."""
        return FakeService(self.missing)


class FakeBleakClient:
    """A BleakClient that serves canned characteristic values."""

    def __init__(
        self, values: dict[str, bytes], missing: set[str] | None = None
    ) -> None:
        """Initialize the client, optionally without some characteristics."""
        self.values = values
        self.written: list[tuple[str, bytes]] = []
        self.notify_callbacks: dict[str, Callable[..., Any]] = {}
        self.is_connected = True
        self.address = VOLCANO_ADDRESS
        self.services = FakeServices(missing or set())

    async def read_gatt_char(self, char: FakeCharacteristic) -> bytearray:
        """Read a characteristic."""
        return bytearray(self.values[char.uuid])

    async def write_gatt_char(self, char: FakeCharacteristic, value: bytearray) -> None:
        """Record a write."""
        self.written.append((char.uuid, bytes(value)))

    async def start_notify(
        self, char: FakeCharacteristic, callback: Callable[..., Any]
    ) -> None:
        """Record a notification subscription."""
        self.notify_callbacks[char.uuid] = callback

    async def disconnect(self) -> None:
        """Disconnect the client."""
        self.is_connected = False


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


async def test_status_registers_decode_the_read_only_modes() -> None:
    """The service, air-step and second-stage bits are decoded, not written."""
    values = default_values()
    prj1v = (
        MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA
        | MASK_PRJSTAT1_VOLCANO_SECOND_STAGE
        | MASK_PRJSTAT1_VOLCANO_AIR_STEP_MODE
    )
    values[CHARACTERISTIC_PRJ1V] = prj1v.to_bytes(2, "little")
    values[CHARACTERISTIC_PRJ2V] = MASK_PRJSTAT2_VOLCANO_SERVICE_MODE.to_bytes(
        2, "little"
    )
    client = FakeBleakClient(values)
    volcano, _, _ = await connect(client)

    data = volcano.data
    assert data.second_stage is True
    assert data.air_step_mode is True
    assert data.service_mode is True
    # None of them is an error condition on its own.
    assert data.prv1_error is False
    assert data.prv2_error is False

    # And they follow the device back down again.
    callback = client.notify_callbacks[CHARACTERISTIC_PRJ1V]
    await callback(
        FakeCharacteristic(CHARACTERISTIC_PRJ1V),
        bytearray(MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA.to_bytes(2, "little")),
    )

    assert data.second_stage is False
    assert data.air_step_mode is False


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

    assert (CHARACTERISTIC_SET_TEMP, (1950).to_bytes(2, "little")) in client.written
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
    assert (CHARACTERISTIC_SET_TEMP, (2000).to_bytes(2, "little")) in client.written


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
