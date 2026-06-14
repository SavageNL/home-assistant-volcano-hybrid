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
    CHARACTERISTIC_LED_BRIGHTNESS,
    CHARACTERISTIC_PRJ1V,
    CHARACTERISTIC_PRJ2V,
    CHARACTERISTIC_PRJ3V,
    CHARACTERISTIC_SERIAL_NUMBER,
    CHARACTERISTIC_SET_TEMP,
    CHARACTERISTIC_SHUT_OFF,
    MASK_PRJSTAT1_VOLCANO_HEIZUNG_ENA,
    MASK_PRJSTAT1_VOLCANO_PUMPE_FET_ENABLE,
    MASK_PRJSTAT2_VOLCANO_DISPLAY_ON_COOLING,
    MASK_PRJSTAT2_VOLCANO_FAHRENHEIT_ENA,
    MASK_PRJSTAT3_VOLCANO_VIBRATION,
    VolcanoBLE,
)

from . import VOLCANO_ADDRESS, make_ble_device, make_service_info

if TYPE_CHECKING:
    from collections.abc import Callable

ESTABLISH_CONNECTION = (
    "custom_components.volcano_hybrid.volcano_ble.volcano_ble.establish_connection"
)


class FakeCharacteristic:
    """A GATT characteristic that only knows its uuid."""

    def __init__(self, uuid: str) -> None:
        """Initialize the characteristic."""
        self.uuid = uuid


class FakeService:
    """A GATT service handing out characteristics."""

    def get_characteristic(self, uuid: str) -> FakeCharacteristic:
        """Get a characteristic by uuid."""
        return FakeCharacteristic(uuid)


class FakeServices:
    """A GATT service collection."""

    def get_service(self, uuid: str) -> FakeService:
        """Get a service by uuid."""
        return FakeService()


class FakeBleakClient:
    """A BleakClient that serves canned characteristic values."""

    def __init__(self, values: dict[str, bytes]) -> None:
        """Initialize the client."""
        self.values = values
        self.written: list[tuple[str, bytes]] = []
        self.notify_callbacks: dict[str, Callable[..., Any]] = {}
        self.is_connected = True
        self.address = VOLCANO_ADDRESS
        self.services = FakeServices()

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
        CHARACTERISTIC_SERIAL_NUMBER: b"VH123456 ",
        CHARACTERISTIC_FIRMWARE_VERSION: b"V01.23",
        CHARACTERISTIC_FIRMWARE_BLE_VERSION: b"V01.00",
        CHARACTERISTIC_BOOTLOADER_VERSION: b"V00.90",
        CHARACTERISTIC_FIRMWARE: b"FW",
        CHARACTERISTIC_CURRENT_AUTO_OFF_TIME: (1200).to_bytes(2, "little"),
        CHARACTERISTIC_HEAT_HOURS_CHANGED: (2).to_bytes(2, "little"),
        CHARACTERISTIC_HEAT_MINUTES_CHANGED: (30).to_bytes(2, "little"),
        CHARACTERISTIC_SHUT_OFF: (1800).to_bytes(2, "little"),
        CHARACTERISTIC_LED_BRIGHTNESS: (70).to_bytes(2, "little"),
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
