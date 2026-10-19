"""Fakes of the bleak client shared by the protocol-layer tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bleak import BleakError

from . import VOLCANO_ADDRESS

if TYPE_CHECKING:
    from collections.abc import Callable


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
        self,
        values: dict[str, bytes],
        missing: set[str] | None = None,
        address: str = VOLCANO_ADDRESS,
    ) -> None:
        """Initialize the client, optionally without some characteristics."""
        self.values = values
        self.written: list[tuple[str, bytes]] = []
        self.notify_callbacks: dict[str, Callable[..., Any]] = {}
        self.is_connected = True
        self.address = address
        self.services = FakeServices(missing or set())
        self.cache_clears = 0

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

    async def clear_cache(self) -> bool:
        """Record that the cached service table was dropped."""
        self.cache_clears += 1
        return True


class SimulatedQvap:
    """
    A Venty/Veazy behind a FakeBleakClient.

    Every write to the control characteristic is answered through the notify
    callback with the full reply for that command, the way the device does:
    a status write is applied to the state and answered with the new status.
    Commands listed in ``mute`` are recorded but never answered; writing one
    listed in ``fail`` raises BleakError, as a dropped link does.
    """

    def __init__(self, client: FakeBleakClient, *, veazy: bool = False) -> None:
        """Attach to the client and start from a heating, charging device."""
        self.client = client
        self.veazy = veazy
        # 184 °C of 186 °C, boost 10, superboost 20, 85 %, 120 s, heating,
        # charging, setpoint reached.
        # Bytes 16-19 (settings2, its mask, two unknown) start out zero.
        self.status = bytearray(
            [0x01, 0, 0x2E, 0x07, 0x44, 0x07, 10, 20, 85, 0x78, 0, 1, 0, 1, 0x02, 0]
        ) + bytearray(4)
        self.firmware_flags = 0x01
        self.settings6 = bytearray([0x06, 0, 7, 0, 0, 1, 0])
        self.sent: list[bytes] = []
        self.mute: set[int] = set()
        self.fail: set[int] = set()
        client.write_gatt_char = self._write  # type: ignore[method-assign]

    async def _write(
        self, char: FakeCharacteristic, value: bytearray, response: bool = True
    ) -> None:
        frame = bytes(value)
        if frame[0] in self.fail:
            msg = f"write of 0x{frame[0]:02x} failed"
            raise BleakError(msg)
        self.client.written.append((char.uuid, frame))
        self.sent.append(frame)
        if frame[0] in self.mute:
            return
        reply = self._reply(frame)
        callback = self.client.notify_callbacks.get(char.uuid)
        if reply is not None and callback is not None:
            await callback(char, bytearray(reply))

    def _reply(self, frame: bytes) -> bytes | None:
        handlers: dict[int, Callable[[bytes], bytes]] = {
            0x01: self._status_reply,
            0x02: self._firmware_reply,
            0x04: self._usage_reply,
            0x05: self._identity_reply,
            0x06: self._settings6_reply,
        }
        if (handler := handlers.get(frame[0])) is not None:
            return handler(frame)
        fixed = {0x1D: bytes([0x1D, 0x00]), 0x0D: bytes([0x0D, 0x01])}
        return fixed.get(frame[0])

    def _status_reply(self, frame: bytes) -> bytes:
        mask = frame[1]
        if mask & 0x02:
            self.status[4:6] = frame[4:6]
        if mask & 0x04:
            self.status[6] = frame[6]
        if mask & 0x08:
            self.status[7] = frame[7]
        if mask & 0x20:
            self.status[11] = frame[11]
        if mask & 0x80:
            self.status[14] = (self.status[14] & ~frame[15]) | (frame[14] & frame[15])
            self.status[16] = (self.status[16] & ~frame[17]) | (frame[16] & frame[17])
        return bytes(self.status)

    def _firmware_reply(self, _: bytes) -> bytes:
        flags = bytes([0x02, self.firmware_flags])
        return flags + b"V01.09" + bytes(3) + b"V00.05" + bytes(3)

    def _usage_reply(self, _: bytes) -> bytes:
        heater = (150).to_bytes(3, "little")
        charging = (40).to_bytes(3, "little")
        return bytes([0x04]) + heater + charging + bytes(13)

    def _identity_reply(self, _: bytes) -> bytes:
        reply = bytearray(20)
        reply[0] = 0x05
        reply[9:15] = b"654321" if self.veazy else b"123456"
        reply[15:17] = b"VZ" if self.veazy else b"VY"
        reply[18] = 3
        return bytes(reply)

    def _settings6_reply(self, frame: bytes) -> bytes:
        mask = frame[1]
        if mask & 0x01:
            self.settings6[2] = frame[2]
        if mask & 0x08:
            self.settings6[5] = frame[5]
        if mask & 0x10:
            self.settings6[6] = frame[6]
        return bytes(self.settings6)
