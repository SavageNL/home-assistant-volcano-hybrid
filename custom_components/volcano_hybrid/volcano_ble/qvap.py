"""Venty / Veazy protocol (VENTY_BLE_SPEC.md)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak import BleakError

from . import qvap_frames as f
from .const import DeviceFamily
from .device import StorzBickelDevice, UnsupportedCommandError, _decode_ascii
from .qvap_data import QvapData, VeazyData, VentyData

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakClient, BLEDevice

_LOGGER = logging.getLogger(__name__)

SERVICE_UUID = "00000000-5354-4f52-5a26-4249434b454c"
CHAR_CONTROL = "00000001-5354-4f52-5a26-4249434b454c"
GAP_SERVICE_UUID = "00001800-0000-1000-8000-00805f9b34fb"
CHAR_GAP_NAME = "00002a00-0000-1000-8000-00805f9b34fb"

# The device does not push (spec §1.2): the vendor app polls every 500 ms.
# One second is plenty for Home Assistant and half the radio time.
QVAP_POLL_INTERVAL = 1.0
# The usage counters and the 0x06 settings barely move; the app refreshes the
# counters every ~15 s.
QVAP_SLOW_POLL_EVERY = 30
# How long the connect waits for the firmware reply that says whether the
# application or the bootloader is running (spec §3.1).
FIRMWARE_REPLY_TIMEOUT = 5.0
# Sent once the firmware reply has confirmed the application runs (spec §4).
# 0x23 (analysis key) and [0x01, 0x06] (connection interval) are skipped.
INIT_COMMANDS = (f.CMD_ADVERTISING, f.CMD_STATUS, f.CMD_USAGE, f.CMD_IDENTITY)


class QvapDevice(StorzBickelDevice):
    """A device speaking the Qvap frame protocol."""

    data: QvapData

    def __init__(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
        *,
        device: BLEDevice | None = None,
    ) -> None:
        """Initialize, with no poll task until connected."""
        super().__init__(data_updated, device_updated, device=device)
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_tick = 0
        self._firmware_reply = asyncio.Event()

    # -- connection --------------------------------------------------------

    async def _async_read_initial(self) -> None:
        client = self.client
        if client is None:
            return
        # Whatever the device was last time, it may have entered its bootloader
        # since: nothing but the firmware query is sent until it says again.
        self.data.forget_mode()
        # A half-finished init would leave a connection nothing ever re-reads
        # (no mode, no poll): drop it so the coordinator's reconnect retries.
        try:
            if not await self._async_init_sequence(client):
                _LOGGER.debug("No firmware reply from the %s", self.family)
                await self.async_disconnect()
                return
        except BleakError as err:
            _LOGGER.debug("Initialising the %s failed: %s", self.family, err)
            await self.async_disconnect()
            return
        _LOGGER.debug("Initial %s frames read", self.family)
        self._after_data_updated()
        self._after_device_updated()
        # The link can drop partway through the init; nothing to poll then.
        if self.data.bootloader_mode is False and self.is_connected:
            self._start_polling()

    async def _async_init_sequence(self, client: BleakClient) -> bool:
        """Subscribe and send the connect sequence; False without a firmware reply."""
        control = self._get_characteristic(client, SERVICE_UUID, CHAR_CONTROL)
        await client.start_notify(control, self._on_notify)
        await self._async_read_optional(
            GAP_SERVICE_UUID, CHAR_GAP_NAME, self._parse_gap_name
        )
        if not await self._async_query_firmware():
            return False
        if self.data.bootloader_mode is False:
            for cmd in INIT_COMMANDS:
                await self._async_write_frame(f.build_request(cmd))
            await self._async_write_frame(f.build_settings6_write(0))
        else:
            # Queued commands are for the application; never replay them here.
            self.data.clear_open_writes()
            _LOGGER.warning(
                "The %s is in its bootloader; it is reported, not controlled",
                self.family,
            )
        return True

    async def _async_query_firmware(self) -> bool:
        """Ask for the firmware info and wait for the reply (spec §3.1)."""
        self._firmware_reply.clear()
        if not await self._async_write_frame(f.build_request(f.CMD_FIRMWARE)):
            return False
        try:
            async with asyncio.timeout(FIRMWARE_REPLY_TIMEOUT):
                await self._firmware_reply.wait()
        except TimeoutError:
            return False
        return True

    async def _async_refresh(self) -> None:
        if self.is_connected and self.data.bootloader_mode is False:
            await self._async_write_frame(f.build_request(f.CMD_STATUS))

    def _on_disconnected(self) -> None:
        self._stop_polling()

    async def async_disconnect(self) -> None:
        """Disconnect, and wait for the poll loop to have finished."""
        task = self._poll_task
        await super().async_disconnect()
        self._stop_polling()
        if task is not None and task is not asyncio.current_task():
            await asyncio.wait({task})

    # -- polling -----------------------------------------------------------

    def _start_polling(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._poll_tick = 0
        self._poll_task = asyncio.create_task(
            self._async_poll_loop(), name=f"{self.family} poll"
        )

    def _stop_polling(self) -> None:
        task, self._poll_task = self._poll_task, None
        # The loop disconnecting itself ends on its own; cancelling it would
        # abort that disconnect halfway.
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _async_poll_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(QVAP_POLL_INTERVAL)
                if not self.is_connected:
                    return
                await self._async_poll_once()
        except BleakError as err:
            _LOGGER.debug("Polling the %s failed, disconnecting: %s", self.family, err)
            await self.async_disconnect()
        except Exception:
            # Anything else would end the loop silently and leave a connection
            # nobody polls; disconnect so the coordinator reconnects.
            _LOGGER.exception("Unexpected error polling the %s", self.family)
            await self.async_disconnect()

    async def _async_poll_once(self) -> None:
        """One poll: the status, and every 30th time the slow-moving values."""
        if self.data.bootloader_mode is not False:
            return
        self._poll_tick += 1
        if self._poll_tick % QVAP_SLOW_POLL_EVERY == 0:
            await self._async_write_frame(f.build_request(f.CMD_USAGE))
            await self._async_write_frame(f.build_settings6_write(0))
        await self._async_write_frame(f.build_request(f.CMD_STATUS))

    # -- frames ------------------------------------------------------------

    def _check_sendable(self, cmd: int) -> None:
        """Refuse anything that could put the device into or drive its bootloader."""
        if cmd in f.FORBIDDEN_COMMANDS:
            msg = f"command 0x{cmd:02x} is never sent (spec §3.8)"
            raise UnsupportedCommandError(msg)
        # Only the firmware query (which tells the modes apart) goes to a device
        # whose mode is not known; in the bootloader 0x01 is even the page-write
        # command (spec §3.8), and nothing else is documented there.
        if cmd != f.CMD_FIRMWARE and self.data.bootloader_mode is not False:
            msg = f"command 0x{cmd:02x} is only sent to a running application"
            raise UnsupportedCommandError(msg)

    async def _async_write_frame(self, frame: bytes) -> bool:
        """Send one frame, refusing anything that could touch the bootloader."""
        cmd = frame[0]
        self._check_sendable(cmd)
        # Connecting runs the init sequence, which settles the mode afresh:
        # check again once connected, before anything is written.
        if not await self._ensure_client_connected():
            return False
        self._check_sendable(cmd)
        # Written directly rather than through _write_gatt, which would connect
        # again (unchecked) if the connection above was dropped meanwhile.
        client = self.client
        if client is None or not client.is_connected:
            return False
        char = self._get_characteristic(client, SERVICE_UUID, CHAR_CONTROL)
        await client.write_gatt_char(char, bytearray(frame))
        return True

    async def _on_notify(self, _: object, data: bytearray) -> None:
        frame = bytes(data)
        try:
            self._apply_frame(frame)
        except ValueError as err:
            _LOGGER.debug(
                "Ignoring malformed %s frame %s: %s", self.family, frame.hex(), err
            )
            return
        self._after_data_updated()

    def _apply_frame(self, frame: bytes) -> None:
        if not frame:
            return
        cmd = frame[0]
        if cmd == f.CMD_STATUS:
            self.data.apply_status(f.parse_status(frame))
        elif cmd == f.CMD_FIRMWARE:
            self.data.apply_firmware(f.parse_firmware(frame))
            self._firmware_reply.set()
            self._after_device_updated()
        elif cmd == f.CMD_USAGE:
            self.data.apply_usage(f.parse_usage(frame))
        elif cmd == f.CMD_IDENTITY:
            self.data.apply_identity(f.parse_identity(frame))
            self._after_device_updated()
        elif cmd == f.CMD_SETTINGS:
            self.data.apply_settings6(f.parse_settings6(frame))
        elif cmd == f.CMD_ADVERTISING:
            self.data.find_mode = f.parse_advertising(frame)
        else:
            _LOGGER.debug("Unhandled %s frame 0x%02x", self.family, cmd)

    def _parse_gap_name(self, data: bytearray) -> None:
        # "S&B VY123456": the serial is the second word (spec §1).
        parts = _decode_ascii(data).split(" ")
        if len(parts) > 1 and self.data.serial_number is None:
            self.data.serial_number = parts[1]

    # -- commands ----------------------------------------------------------

    def _require_application(self) -> None:
        if self.data.bootloader_mode is not False:
            msg = "the device is not known to be running its application"
            raise UnsupportedCommandError(msg)

    async def async_set_heater(self, on: bool) -> bool:
        """Switch between off and normal heating; the reply confirms."""
        self._require_application()
        self.data.heater_write = on
        written = await self._async_send_pending(
            self._async_write_frame(f.build_heater_write(on)),
            lambda: self.data.discard_heater_write(on),
        )
        self._after_data_updated()
        return written

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the base target temperature."""
        self._require_application()
        self.data.set_temp_write = int(target)
        written = await self._async_send_pending(
            self._async_write_frame(f.build_target_write(int(target))),
            lambda: self.data.discard_set_temp_write(int(target)),
        )
        self._after_data_updated()
        return written

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset."""
        self._require_application()
        return await self._async_write_frame(f.build_boost_write(offset))

    async def async_set_superboost_temperature(self, offset: int) -> bool:
        """Set the superboost offset."""
        self._require_application()
        return await self._async_write_frame(f.build_superboost_write(offset))

    async def _async_set_bit(self, bit: int, on: bool) -> bool:
        """Write one known settings bit; nothing else in byte 14 is masked."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings_write(bit if on else 0, bit)
        )

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Bit 0 is *Fahrenheit*."""
        return await self._async_set_bit(f.BIT_FAHRENHEIT, not on)

    async def async_set_charge_optimization(self, on: bool) -> bool:
        """Charge more slowly to spare the battery."""
        return await self._async_set_bit(f.BIT_CHARGE_OPTIMIZATION, on)

    async def async_set_charge_limit(self, on: bool) -> bool:
        """Stop charging short of 100 %."""
        return await self._async_set_bit(f.BIT_CHARGE_LIMIT, on)

    async def async_set_boost_visualization(self, on: bool) -> bool:
        """Show boost on the display; the Veazy stores the bit inverted."""
        return await self._async_set_bit(
            f.BIT_BOOST_VISUALIZATION, on != self.data.INVERT_BOOST_VISUALIZATION
        )

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Only the Veazy branch of the vendor app writes this (spec §2.3)."""
        if self.family is not DeviceFamily.VEAZY:
            msg = "permanent Bluetooth is only written on a Veazy"
            raise UnsupportedCommandError(msg)
        self._require_application()
        bit = f.BIT2_PERMANENT_BLUETOOTH
        return await self._async_write_frame(
            f.build_settings_write(0, 0, bit if on else 0, bit)
        )

    async def async_set_brightness(self, brightness: int) -> bool:
        """Display brightness 1-9."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_BRIGHTNESS, brightness=brightness)
        )

    async def async_set_vibration(self, on: bool) -> bool:
        """Vibration on or off."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_VIBRATION, vibration=on)
        )

    async def async_set_boost_timeout_disabled(self, on: bool) -> bool:
        """Whether boost never times out."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_BOOST_TIMEOUT, timeout_disabled=on)
        )

    async def async_find_device(self) -> bool:
        """Make the device signal so it can be found."""
        self._require_application()
        return await self._async_write_frame(f.build_find_device())

    # -- pending writes ----------------------------------------------------

    async def _async_try_ensure_written_values(self) -> None:
        if not self.is_connected or self.data.bootloader_mode is not False:
            return
        if (
            self.data.heater_needs_write or self.data.set_temp_needs_write
        ) and not self.data.is_on:
            # Never turn the device on by replaying a command it missed.
            self.data.clear_open_writes()
        with self._replaying():
            if (
                self.data.heater_needs_write
                and (on := self.data.heater_write) is not None
            ):
                await self.async_set_heater(on)
            if (
                self.data.set_temp_needs_write
                and (target := self.data.set_temp_write) is not None
            ):
                await self.async_set_target_temperature(target)


class VentyDevice(QvapDevice):
    """A Venty."""

    family = DeviceFamily.VENTY
    data_class = VentyData


class VeazyDevice(QvapDevice):
    """A Veazy."""

    family = DeviceFamily.VEAZY
    data_class = VeazyData
