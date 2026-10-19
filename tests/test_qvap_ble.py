"""Tests for the Venty/Veazy protocol against a simulated device."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError

from custom_components.volcano_hybrid.volcano_ble import qvap_frames as f
from custom_components.volcano_hybrid.volcano_ble.device import UnsupportedCommandError
from custom_components.volcano_hybrid.volcano_ble.qvap import (
    CHAR_CONTROL,
    CHAR_GAP_NAME,
    QvapDevice,
    VeazyDevice,
    VentyDevice,
)

from . import make_ble_device
from .fakes import FakeBleakClient, FakeCharacteristic, SimulatedQvap

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

ESTABLISH = "custom_components.volcano_hybrid.volcano_ble.device.establish_connection"
QVAP = "custom_components.volcano_hybrid.volcano_ble.qvap"


def _client(name: bytes = b"S&B VY123456") -> FakeBleakClient:
    return FakeBleakClient({CHAR_GAP_NAME: name})


async def connect(*, veazy: bool = False) -> tuple[QvapDevice, SimulatedQvap]:
    """Connect a device to a simulated one, without the background poll."""
    client = _client()
    simulated = SimulatedQvap(client, veazy=veazy)
    device = (VeazyDevice if veazy else VentyDevice)(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch.object(QvapDevice, "_start_polling"),
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    return device, simulated


async def test_connect_runs_the_init_sequence_and_reads_everything() -> None:
    """The connect sends 0x02, 0x1D, 0x01, 0x04, 0x05, 0x06 and decodes them."""
    device, simulated = await connect()
    assert device.is_connected
    assert [frame[0] for frame in simulated.sent][:6] == [
        0x02,
        0x1D,
        0x01,
        0x04,
        0x05,
        0x06,
    ]
    data = device.data
    assert data.firmware_version == "V01.09"
    assert data.bootloader_mode is False
    assert data.current_temp == 184
    assert data.set_temp == 186
    assert data.battery == 85
    assert data.heater is True
    assert data.serial_number == "VY123456"
    assert data.heat_time == 150
    assert data.brightness == 7
    assert data.find_mode is False


async def test_writes_are_confirmed_by_the_reply() -> None:
    """A status write is answered with the new status, confirming it."""
    device, simulated = await connect()
    simulated.sent.clear()

    assert await device.async_set_target_temperature(190)
    assert simulated.sent[0] == f.build_target_write(190)
    assert device.data.set_temp == 190
    assert not device.data.is_assumed

    assert await device.async_set_heater(False)
    assert simulated.sent[-1] == f.build_heater_write(False)
    assert device.data.heater is False

    assert await device.async_set_boost_temperature(12)
    assert device.data.boost_temp == 12
    assert await device.async_set_superboost_temperature(25)
    assert device.data.superboost_temp == 25


async def test_settings_writes() -> None:
    """Settings bits and command-0x06 fields are written masked."""
    device, simulated = await connect()
    simulated.sent.clear()
    assert await device.async_set_charge_limit(True)
    assert simulated.sent[-1] == f.build_settings_write(
        f.BIT_CHARGE_LIMIT, f.BIT_CHARGE_LIMIT
    )
    assert device.data.charge_limit is True
    assert await device.async_set_charge_optimization(True)
    assert device.data.charge_optimization is True
    assert await device.async_set_showing_celsius(False)
    assert simulated.sent[-1] == f.build_settings_write(
        f.BIT_FAHRENHEIT, f.BIT_FAHRENHEIT
    )
    assert device.data.showing_celsius is False
    assert await device.async_set_brightness(3)
    assert simulated.sent[-1] == f.build_settings6_write(
        f.CMD6_BRIGHTNESS, brightness=3
    )
    assert device.data.brightness == 3
    assert await device.async_set_vibration(False)
    assert device.data.vibration is False
    assert await device.async_set_boost_timeout_disabled(True)
    assert device.data.boost_timeout_disabled is True
    assert await device.async_find_device()
    assert simulated.sent[-1] == f.build_find_device()


async def test_settings_writes_never_touch_the_factory_reset_bit() -> None:
    """Bit 0x04 of byte 14 resets the device (spec §2.3): no write sets or masks it."""
    device, simulated = await connect(veazy=True)
    simulated.sent.clear()
    for on in (True, False):
        await device.async_set_showing_celsius(on)
        await device.async_set_charge_optimization(on)
        await device.async_set_charge_limit(on)
        await device.async_set_boost_visualization(on)
        await device.async_set_permanent_bluetooth(on)
    status_writes = [frame for frame in simulated.sent if frame[0] == f.CMD_STATUS]
    assert status_writes
    for frame in status_writes:
        assert not frame[14] & 0x04
        assert not frame[15] & 0x04


async def test_veazy_inverts_visualization_and_writes_permanent_bluetooth() -> None:
    """The Veazy stores visualisation inverted and can write settings2."""
    device, simulated = await connect(veazy=True)
    simulated.sent.clear()
    assert await device.async_set_boost_visualization(True)
    assert simulated.sent[-1] == f.build_settings_write(0, f.BIT_BOOST_VISUALIZATION)
    assert device.data.boost_visualization is True
    assert await device.async_set_permanent_bluetooth(True)
    assert simulated.sent[-1] == f.build_settings_write(
        0, 0, f.BIT2_PERMANENT_BLUETOOTH, f.BIT2_PERMANENT_BLUETOOTH
    )
    assert device.data.permanent_bluetooth is True
    assert device.data.color == "pink"


async def test_venty_writes_visualization_as_is() -> None:
    """On a Venty the visualisation bit means what it says."""
    device, simulated = await connect()
    assert await device.async_set_boost_visualization(True)
    assert simulated.sent[-1] == f.build_settings_write(
        f.BIT_BOOST_VISUALIZATION, f.BIT_BOOST_VISUALIZATION
    )
    assert device.data.boost_visualization is True


async def test_venty_refuses_to_write_permanent_bluetooth() -> None:
    """Only the Veazy branch of the vendor app writes permanent Bluetooth."""
    device, simulated = await connect()
    simulated.sent.clear()
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_permanent_bluetooth(True)
    assert simulated.sent == []


async def test_bootloader_mode_blocks_control() -> None:
    """A device in its bootloader is reported, never driven (spec §3.1, §3.8)."""
    client = _client()
    simulated = SimulatedQvap(client)
    simulated.firmware_flags = 0x10
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch.object(QvapDevice, "_start_polling") as start_polling,
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert device.data.bootloader_mode is True
    assert device.data.invalid_application is True
    # Nothing but the firmware query reached a device in its bootloader.
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]
    start_polling.assert_not_called()
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_heater(True)
    with pytest.raises(UnsupportedCommandError):
        await device.async_find_device()
    with pytest.raises(UnsupportedCommandError):
        await device._async_write_frame(f.build_request(f.CMD_STATUS))  # noqa: SLF001
    await device._async_poll_once()  # noqa: SLF001
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]


async def test_status_is_not_sent_before_the_mode_is_known() -> None:
    """Until the firmware reply says "application", 0x01 is never sent."""
    device = VentyDevice(lambda: None, lambda: None)
    assert device.data.bootloader_mode is None
    with pytest.raises(UnsupportedCommandError):
        await device._async_write_frame(f.build_request(f.CMD_STATUS))  # noqa: SLF001
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_target_temperature(190)


async def test_command_without_a_device_to_connect_to_is_not_written() -> None:
    """With nothing to connect to, a command reports it was not written."""
    device = VentyDevice(lambda: None, lambda: None)
    device.data.bootloader_mode = False
    assert not await device.async_set_heater(True)


async def test_unanswered_firmware_query_disconnects() -> None:
    """Without the firmware reply the mode is unknown: give up, send nothing else."""
    client = _client()
    simulated = SimulatedQvap(client)
    simulated.mute.add(f.CMD_FIRMWARE)
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch(f"{QVAP}.FIRMWARE_REPLY_TIMEOUT", 0),
        patch.object(QvapDevice, "_start_polling") as start_polling,
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert not device.is_connected
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]
    start_polling.assert_not_called()


async def test_missing_control_characteristic_clears_the_service_cache() -> None:
    """Every Qvap serves the control characteristic: without it the table is stale."""
    client = FakeBleakClient({CHAR_GAP_NAME: b"S&B VY123456"}, missing={CHAR_CONTROL})
    device = VentyDevice(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert not device.is_connected
    assert client.cache_clears == 1


async def test_reconnect_forgets_the_previous_mode() -> None:
    """A reconnect asks for the mode again before trusting it."""
    device, simulated = await connect()
    await device.async_disconnect()
    simulated.firmware_flags = 0x00
    simulated.sent.clear()
    simulated.client.is_connected = True
    with (
        patch(ESTABLISH, AsyncMock(return_value=simulated.client)),
        patch.object(QvapDevice, "_start_polling"),
    ):
        await device.async_manual_update()
    assert device.data.bootloader_mode is True
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]


async def test_command_that_reconnects_to_a_bootloader_is_refused() -> None:
    """A command that has to reconnect first is checked against the new mode."""
    device, simulated = await connect()
    await device.async_disconnect()
    simulated.firmware_flags = 0x00
    simulated.sent.clear()
    simulated.client.is_connected = True
    with (
        patch(ESTABLISH, AsyncMock(return_value=simulated.client)),
        patch.object(QvapDevice, "_start_polling"),
        pytest.raises(UnsupportedCommandError),
    ):
        await device.async_set_heater(True)
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]
    # The refused write is not left behind as a pending one.
    assert device.data.heater_write is None
    assert not device.data.is_assumed


@pytest.mark.parametrize(
    "command",
    [
        lambda device: device.async_find_device(),
        lambda device: device.async_set_brightness(3),
        lambda device: device.async_set_vibration(False),
        lambda device: device.async_set_target_temperature(190),
    ],
    ids=["find_device", "brightness", "vibration", "target"],
)
async def test_no_control_frame_reaches_a_reconnected_bootloader(
    command: Callable[[QvapDevice], Awaitable[bool]],
) -> None:
    """Whatever the command, only 0x02 reaches a device found in its bootloader."""
    device, simulated = await connect()
    await device.async_disconnect()
    simulated.firmware_flags = 0x00
    simulated.sent.clear()
    simulated.client.is_connected = True
    with (
        patch(ESTABLISH, AsyncMock(return_value=simulated.client)),
        patch.object(QvapDevice, "_start_polling"),
        pytest.raises(UnsupportedCommandError),
    ):
        await command(device)
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]
    assert not device.data.is_assumed


async def test_command_after_an_unanswered_reconnect_is_not_sent() -> None:
    """A reconnect that gets no firmware reply leaves nothing to write to."""
    device, simulated = await connect()
    await device.async_disconnect()
    simulated.mute.add(f.CMD_FIRMWARE)
    simulated.sent.clear()
    simulated.client.is_connected = True
    establish = AsyncMock(return_value=simulated.client)
    with (
        patch(ESTABLISH, establish),
        patch(f"{QVAP}.FIRMWARE_REPLY_TIMEOUT", 0),
        patch.object(QvapDevice, "_start_polling"),
        pytest.raises(UnsupportedCommandError),
    ):
        await device.async_set_brightness(3)
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]
    assert establish.await_count == 1


async def test_pending_write_does_not_survive_a_reconnect_into_the_bootloader() -> None:
    """A queued write is dropped, not replayed or raised, in the bootloader."""
    device, simulated = await connect()
    simulated.mute.add(f.CMD_STATUS)
    await device.async_set_target_temperature(200)
    assert device.data.is_assumed
    await device.async_disconnect()
    simulated.mute.clear()
    simulated.firmware_flags = 0x00
    simulated.sent.clear()
    simulated.client.is_connected = True
    with (
        patch(ESTABLISH, AsyncMock(return_value=simulated.client)),
        patch.object(QvapDevice, "_start_polling"),
    ):
        await device.async_manual_update()
    assert device.data.bootloader_mode is True
    assert not device.data.is_assumed
    assert [frame[0] for frame in simulated.sent] == [f.CMD_FIRMWARE]


async def test_pending_writes_are_not_replayed_while_disconnected() -> None:
    """Replaying needs a connection whose mode is known."""
    device, simulated = await connect()
    simulated.mute.add(f.CMD_STATUS)
    await device.async_set_target_temperature(200)
    simulated.client.is_connected = False
    simulated.sent.clear()
    await device._async_try_ensure_written_values()  # noqa: SLF001
    assert simulated.sent == []
    assert device.data.set_temp_write == 200


async def test_failed_subscription_disconnects() -> None:
    """A connect whose notify subscription fails is dropped, not kept half-alive."""
    client = _client()
    simulated = SimulatedQvap(client)
    client.start_notify = AsyncMock(  # type: ignore[method-assign]
        side_effect=BleakError("no notify")
    )
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch.object(QvapDevice, "_start_polling") as start_polling,
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert not device.is_connected
    assert simulated.sent == []
    start_polling.assert_not_called()


async def test_failed_firmware_write_disconnects() -> None:
    """A connect whose firmware query cannot be written is dropped."""
    client = _client()
    simulated = SimulatedQvap(client)
    simulated.fail.add(f.CMD_FIRMWARE)
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch.object(QvapDevice, "_start_polling") as start_polling,
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert not device.is_connected
    assert device.data.bootloader_mode is None
    assert simulated.sent == []
    start_polling.assert_not_called()


async def test_forbidden_commands_are_never_sent() -> None:
    """The bootloader switch and bootloader commands are refused outright."""
    device, simulated = await connect()
    for cmd in f.FORBIDDEN_COMMANDS:
        with pytest.raises(UnsupportedCommandError):
            await device._async_write_frame(f.build_request(cmd))  # noqa: SLF001
    assert not any(frame[0] in f.FORBIDDEN_COMMANDS for frame in simulated.sent)


async def test_malformed_and_unknown_frames_are_ignored() -> None:
    """A short or unknown notification leaves the state alone."""
    device, simulated = await connect()
    callback = simulated.client.notify_callbacks[CHAR_CONTROL]
    char = FakeCharacteristic(CHAR_CONTROL)
    await callback(char, bytearray([0x01, 0, 0x10]))
    await callback(char, bytearray([0x7F, 0]))
    await callback(char, bytearray())
    assert device.data.current_temp == 184


async def test_gap_name_without_a_serial_is_ignored() -> None:
    """A device name without the serial word leaves the serial to command 0x05."""
    client = _client(b"S&B")
    SimulatedQvap(client)
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch.object(QvapDevice, "_start_polling"),
    ):
        await device.async_manual_update(make_ble_device(name="S&B"))
    assert device.data.serial_number == "VY123456"


async def test_poll_once_sends_status_and_the_slow_commands() -> None:
    """Every poll asks for the status, every 30th also usage and settings."""
    device, simulated = await connect()
    simulated.sent.clear()
    for _ in range(30):
        await device._async_poll_once()  # noqa: SLF001
    sent = [frame[0] for frame in simulated.sent]
    assert sent.count(0x01) == 30
    assert sent.count(0x04) == 1
    assert sent.count(0x06) == 1


async def test_poll_task_starts_and_stops_with_the_connection() -> None:
    """Connecting starts the poll loop; disconnecting ends it."""
    client = _client()
    simulated = SimulatedQvap(client)
    device = VentyDevice(lambda: None, lambda: None)
    with (
        patch(ESTABLISH, AsyncMock(return_value=client)),
        patch(f"{QVAP}.QVAP_POLL_INTERVAL", 0),
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
        task = device._poll_task  # noqa: SLF001
        assert task is not None
        simulated.sent.clear()
        for _ in range(5):
            await asyncio.sleep(0)
        assert f.CMD_STATUS in [frame[0] for frame in simulated.sent]
        await device.async_disconnect()
    assert device._poll_task is None  # noqa: SLF001
    assert task.done()


async def test_start_polling_twice_runs_one_loop() -> None:
    """A second start while the loop runs does not add another loop."""
    device, _ = await connect()
    device._start_polling()  # noqa: SLF001
    task = device._poll_task  # noqa: SLF001
    device._start_polling()  # noqa: SLF001
    assert device._poll_task is task  # noqa: SLF001
    await device.async_disconnect()
    assert task is not None
    assert task.done()


async def test_dropped_connection_stops_polling_and_reconnect_restarts_it() -> None:
    """The disconnect callback ends the loop; the next connect starts a new one."""
    device, simulated = await connect()
    device._start_polling()  # noqa: SLF001
    first = device._poll_task  # noqa: SLF001
    assert first is not None
    simulated.client.is_connected = False
    device._disconnected(simulated.client)  # noqa: SLF001
    assert device._poll_task is None  # noqa: SLF001
    await asyncio.wait({first})

    simulated.client.is_connected = True
    with patch(ESTABLISH, AsyncMock(return_value=simulated.client)):
        await device.async_manual_update()
    second = device._poll_task  # noqa: SLF001
    assert second is not None
    assert second is not first
    await device.async_disconnect()
    assert second.done()


async def test_poll_loop_that_ended_on_its_own_is_replaced() -> None:
    """A loop that finished by itself never blocks the next start."""
    device, simulated = await connect()
    with patch(f"{QVAP}.QVAP_POLL_INTERVAL", 0):
        simulated.client.is_connected = False
        device._start_polling()  # noqa: SLF001
        first = device._poll_task  # noqa: SLF001
        assert first is not None
        await asyncio.wait({first})
        simulated.client.is_connected = True
        device._start_polling()  # noqa: SLF001
        assert device._poll_task is not first  # noqa: SLF001
        await device.async_disconnect()


async def test_bleak_error_while_polling_disconnects() -> None:
    """A failed poll disconnects and ends the loop instead of spinning."""
    device, _ = await connect()
    with (
        patch(f"{QVAP}.QVAP_POLL_INTERVAL", 0),
        patch.object(
            device, "_async_poll_once", AsyncMock(side_effect=BleakError("gone"))
        ) as poll_once,
    ):
        device._start_polling()  # noqa: SLF001
        task = device._poll_task  # noqa: SLF001
        assert task is not None
        await asyncio.wait({task})
    assert poll_once.await_count == 1
    assert not device.is_connected
    assert device._poll_task is None  # noqa: SLF001


async def test_unexpected_error_while_polling_disconnects() -> None:
    """Any other failure also disconnects and ends the loop cleanly."""
    device, _ = await connect()
    with (
        patch(f"{QVAP}.QVAP_POLL_INTERVAL", 0),
        patch.object(
            device, "_async_poll_once", AsyncMock(side_effect=RuntimeError("bug"))
        ),
    ):
        device._start_polling()  # noqa: SLF001
        task = device._poll_task  # noqa: SLF001
        assert task is not None
        await asyncio.wait({task})
    assert task.exception() is None
    assert not device.is_connected
    assert device._poll_task is None  # noqa: SLF001


async def test_pending_heater_write_is_dropped_when_off() -> None:
    """A queued write never turns a device back on that has gone off."""
    device, simulated = await connect()
    simulated.status[11] = 0
    device.data.heater = False
    device.data.set_temp_write = 200
    simulated.sent.clear()
    await device._async_try_ensure_written_values()  # noqa: SLF001
    assert device.data.set_temp_write is None
    assert simulated.sent == []


async def test_pending_target_write_is_replayed_while_on() -> None:
    """An unconfirmed target is sent again while the device heats."""
    device, simulated = await connect()
    simulated.mute.add(f.CMD_STATUS)
    await device.async_set_target_temperature(200)
    assert device.data.is_assumed
    simulated.mute.clear()
    simulated.sent.clear()
    await device._async_try_ensure_written_values()  # noqa: SLF001
    assert simulated.sent == [f.build_target_write(200)]
    assert device.data.set_temp == 200
    assert not device.data.is_assumed


async def test_link_drop_during_the_init_sequence_does_not_deadlock() -> None:
    """
    A link that drops while the connect sends its init frames ends the connect.

    Regression test: the init frames go through _async_write_frame, which
    makes sure the client is connected first. With the link gone that meant a
    connect attempt, which waited for the connect lock the running connect
    already held, so the connect never returned and nothing ever reconnected.
    """
    first, second = _client(), _client()
    simulated = SimulatedQvap(first)
    SimulatedQvap(second)
    device = VentyDevice(lambda: None, lambda: None)
    firmware_reply = simulated._firmware_reply  # noqa: SLF001

    def _reply_then_drop(frame: bytes) -> bytes:
        # The firmware reply arrives, then the link drops.
        first.is_connected = False
        device._disconnected(first)  # type: ignore[arg-type]  # noqa: SLF001
        return firmware_reply(frame)

    simulated._firmware_reply = _reply_then_drop  # type: ignore[method-assign]  # noqa: SLF001
    ble_device = make_ble_device(name="S&B VY123456")
    with (
        patch(ESTABLISH, AsyncMock(side_effect=[first, second])),
        patch.object(QvapDevice, "_start_polling"),
    ):
        async with asyncio.timeout(5):
            await device.async_manual_update(ble_device)
        assert not device.is_connected
        assert not device._connect_lock.locked()  # noqa: SLF001

        # The next update connects again.
        async with asyncio.timeout(5):
            await device.async_manual_update(ble_device)
    assert device.is_connected
    assert device.client is second
