"""The connection and GATT plumbing every Storz & Bickel device shares."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
from typing import TYPE_CHECKING, ClassVar

from bleak import BleakClient, BleakError, BleakGATTCharacteristic, BLEDevice
from bleak.exc import BleakCharacteristicNotFoundError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from .const import FAMILY_MODEL_NAME, DeviceFamily, is_supported
from .data import DeviceData, VolcanoHybridDataStatusProvider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from habluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)

CLEAR_CACHE_TIMEOUT = 10

# The connect attempt the current code runs inside, if any. The connect holds
# the (non-reentrant) connect lock while it reads the initial state, and that
# read can write to the device: the Qvap init frames, or a pending write the
# Volcano or Crafty replays from a read callback. If the link drops meanwhile,
# such a write must not try to connect again, which would wait for the lock
# its own connect holds. A context variable rather than the task identity,
# because the initial read runs part of itself in asyncio.gather child tasks,
# which inherit the context but are other tasks. It holds a token per attempt
# rather than a flag, so a task started during the connect (the Qvap poll
# loop, say) that inherits the context is only exempt while that attempt runs.
_CONNECT_ATTEMPT: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "storz_bickel_connect_attempt", default=None
)


def _decode_ascii(data: bytearray) -> str:
    """
    Decode a characteristic the device serves as ASCII text.

    Undecodable bytes fall back to the hex of what was received. This runs
    inside a read or notification callback, where raising would abort the
    initial read and take the whole connect down — over an identity or
    diagnostic string, on a GATT server that belongs to the BLE module rather
    than the controller, so another module revision answering differently is
    not far-fetched. Reporting the raw bytes leaves whatever it sent legible in
    a bug report instead.
    """
    try:
        return data.decode("ascii").strip()
    except UnicodeDecodeError:
        return data.hex()


class UnsupportedCommandError(Exception):
    """The device cannot carry out this command (family, firmware or mode)."""


class StorzBickelDevice(VolcanoHybridDataStatusProvider):
    """Connection handling shared by every family; subclasses speak the protocol."""

    family: ClassVar[DeviceFamily]
    data_class: ClassVar[type[DeviceData]]

    def __init__(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
        *,
        device: BLEDevice | None = None,
    ) -> None:
        """Initialize the device."""
        super().__init__()
        self._after_data_updated = data_updated
        self._after_device_updated = device_updated
        # Serialize connection attempts: a power-on advertisement burst can
        # otherwise trigger several concurrent establish_connection calls,
        # leaving every client but the last orphaned (never disconnected) and
        # leaking connection slots until Home Assistant restarts.
        self._connect_lock = asyncio.Lock()
        # The token of the connect attempt holding the lock (_CONNECT_ATTEMPT).
        self._connect_attempt: object | None = None
        # Set when a characteristic the protocol requires is missing from the
        # client's service table. The device always serves those, so the table
        # is a stale or incomplete cache (left by another client, or a
        # discovery cut short): reconnecting on the same cache would keep
        # failing until Home Assistant restarts. While set, a disconnect clears
        # the cache and the next connect discovers the services afresh.
        self._services_stale = False
        self.client: BleakClientWithServiceCache | None = None
        self.device = device
        self.data: DeviceData = self.data_class(self)
        self.device_rssi: int | None = None
        self.device_connected_addr: str | None = None

    @staticmethod
    def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if the device is supported."""
        return is_supported(service_info)

    @property
    def rssi(self) -> int | None:
        """Get the device rssi."""
        return self.device_rssi

    @rssi.setter
    def rssi(self, value: int) -> None:
        """Set the device rssi."""
        if self.device_rssi != value:
            self.device_rssi = value
            self._after_data_updated()

    @property
    def connected_addr(self) -> str | None:
        """Get the connected address (when the device is connected, None otherwise)."""
        return self.device_connected_addr if self.is_connected else None

    @connected_addr.setter
    def connected_addr(self, value: str | None) -> None:
        """Set the connected address."""
        if self.device_connected_addr != value:
            self.device_connected_addr = value
            self._after_data_updated()

    @property
    def is_connected(self) -> bool:
        """Return True if the device is connected."""
        return bool(self.client and self.client.is_connected)

    async def async_manual_update(self, device: BLEDevice | None = None) -> DeviceData:
        """
        Trigger an update of the Volcano device data.

        ``device`` is optional because a device that is already connected has
        stopped advertising, so Home Assistant no longer has a ``BLEDevice`` for
        it. The established connection is all this needs.
        """
        if device and device != self.device:
            await self.async_disconnect()
            self.device = device
            self._after_data_updated()

        # This will update when not connected yet
        await self._ensure_client_connected()
        try:
            await self._async_refresh()
            await self._async_try_ensure_written_values()
        except BleakCharacteristicNotFoundError as err:
            # Kept, the link would fail this same way on every poll.
            _LOGGER.debug("Service table is incomplete, reconnecting: %s", err)
            await self.async_disconnect()
        return self.data

    async def _ensure_client_connected(self) -> bool:
        """Ensure the BLE client is initialized and connected."""
        if not self.device:
            _LOGGER.error("No last service info available, unable to connect")
            return False

        # Fast path, deliberately outside the lock: an established connection
        # needs no connect attempt. Waiting for the lock here would deadlock a
        # write that is issued while the connect is still running, because the
        # initial read subscribes and immediately invokes its callbacks, and
        # the auto-off-time callback replays pending writes. That write would
        # wait for the lock held by the connect, which in turn waits for the
        # read that triggered the write.
        if self.is_connected:
            self._determine_connected_device()
            return True

        # Inside this device's own connect the link has dropped since it was
        # established: report that rather than wait for the lock it holds.
        attempt = _CONNECT_ATTEMPT.get()
        if attempt is not None and attempt is self._connect_attempt:
            return False

        async with self._connect_lock:
            attempt = object()
            self._connect_attempt = attempt
            token = _CONNECT_ATTEMPT.set(attempt)
            try:
                return await self._async_connect(self.device)
            finally:
                _CONNECT_ATTEMPT.reset(token)
                self._connect_attempt = None

    async def _async_connect(self, device: BLEDevice) -> bool:
        """Connect and read the initial state, with the connect lock held."""
        # Check connection state under the lock so a burst of concurrent
        # attempts only establishes one connection; the others see the
        # client another attempt just opened.
        if self.is_connected:
            self._determine_connected_device()
            return True

        try:
            _LOGGER.debug("Connecting to BLE device at %s", device.address)
            self.client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                FAMILY_MODEL_NAME[self.family],
                disconnected_callback=self._disconnected,
                use_services_cache=not self._services_stale,
            )
        except BleakNotFoundError as err:
            _LOGGER.debug("BLE device not found while connecting: %s", err)
            await self.async_disconnect()
            return False
        except BleakError as err:
            _LOGGER.debug("Failed to connect to BLE device: %s", err)
            await self.async_disconnect()
            return False

        self._after_data_updated()
        # A required characteristic that cannot be read drops the link: kept,
        # it would leave the device "connected" with half its state unknown and
        # some notifications never subscribed, and nothing would reconnect it to
        # read the rest. Dropped, the next poll or advertisement retries the
        # whole read. Characteristics not every device serves go through
        # _async_read_optional, which never raises, so they cannot cause a
        # reconnect loop. A read over a proxy can time out rather than fail.
        try:
            await self._async_read_and_subscribe_all()
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("Failed to read/subscribe after connect: %r", err)
            await self.async_disconnect()
            return False

        self._determine_connected_device()
        return True

    def _determine_connected_device(self) -> None:
        """
        Determine the connected device address.

        This seems to be what bleak_esphome.backend.client.ESPHomeClient does
        in its constructor
        """
        if self.device is None:
            return
        self.device_connected_addr = self.device.details["source"]

    def _disconnected(self, client: BleakClient) -> None:
        """Handle disconnection events."""
        _LOGGER.debug("Disconnected from BLE device at %s", client.address)
        self.client = None
        self._on_disconnected()
        self._after_data_updated()

    async def _async_read_and_subscribe_all(self) -> DeviceData:
        """Read all required characteristics from the BLE device."""
        await self._async_read_initial()
        # A family's own initial read may drop the link instead of raising.
        if self.is_connected:
            self._services_stale = False
        return self.data

    async def async_disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client:
            if self.client.is_connected:
                if self._services_stale:
                    await self._async_clear_service_cache(self.client)
                await self.client.disconnect()
            self.client = None
            self._on_disconnected()
            self._after_data_updated()

    @staticmethod
    async def _async_clear_service_cache(client: BleakClientWithServiceCache) -> None:
        """
        Drop the cached service table, while the link still stands.

        Cleared on the connection, the backend clears its own cache where it
        can (BlueZ's, or an ESPHome proxy's). Failing is not fatal, since the
        next connect skips the cache either way.
        """
        try:
            async with asyncio.timeout(CLEAR_CACHE_TIMEOUT):
                await client.clear_cache()
        except (BleakError, TimeoutError, OSError, EOFError) as err:
            _LOGGER.debug("Could not clear the service cache: %s", err)

    @staticmethod
    def _find_characteristic(
        client: BleakClient, service_uuid: str, characteristic: str
    ) -> BleakGATTCharacteristic | None:
        """Resolve a characteristic, or None when the table lacks it."""
        service = client.services.get_service(service_uuid)
        return service.get_characteristic(characteristic) if service else None

    def _get_characteristic(
        self, client: BleakClient, service_uuid: str, characteristic: str
    ) -> BleakGATTCharacteristic:
        """Resolve a characteristic the protocol requires."""
        char = self._find_characteristic(client, service_uuid, characteristic)
        if char is None:
            self._services_stale = True
            raise BleakCharacteristicNotFoundError(characteristic)
        return char

    async def _async_read_optional(
        self,
        service_uuid: str,
        characteristic: str,
        value_change_callback: Callable[[bytearray], Awaitable[None] | None],
    ) -> None:
        """
        Read a characteristic that is not known to exist on every device.

        The initial read runs as one asyncio.gather, so a characteristic that a
        firmware or BLE-module revision does not serve would otherwise take the
        whole connect down with it: _get_characteristic raises when it is
        missing, and the remaining reads and subscriptions in the gather never
        happen. Anything read through here leaves its value unset instead and
        the rest of the device still comes up. Its absence is looked up first,
        so it does not mark the service table stale either.
        """
        client = self.client
        if client is None or not client.is_connected:
            return
        if self._find_characteristic(client, service_uuid, characteristic) is None:
            _LOGGER.debug("Optional characteristic %s is not served", characteristic)
            return
        try:
            await self._async_read_and_subscribe(
                service_uuid, characteristic, value_change_callback, subscribe=False
            )
        except BleakError as err:
            _LOGGER.debug(
                "Optional characteristic %s is unavailable: %s", characteristic, err
            )

    async def _async_read_and_subscribe(
        self,
        service_uuid: str,
        characteristic: str,
        value_change_callback: Callable[[bytearray], Awaitable[None] | None],
        subscribe: bool,
    ) -> None:
        """Read a characteristic from the BLE device."""
        client = self.client
        if client is None or not client.is_connected:
            return

        async def _async_call_callback(data: bytearray) -> None:
            result = value_change_callback(data)
            if inspect.isawaitable(result):
                await result

        char = self._get_characteristic(client, service_uuid, characteristic)
        current_value = await client.read_gatt_char(char)
        if (
            subscribe and client.is_connected
        ):  # We just awaited a read, we could be disconnected now
            try:

                async def _async_callback(
                    _: BleakGATTCharacteristic, data: bytearray
                ) -> None:
                    await _async_call_callback(data)
                    self._after_data_updated()

                await client.start_notify(char, _async_callback)
            except BleakError:
                await self.async_disconnect()

        await _async_call_callback(current_value)

    async def _write_gatt(
        self,
        service_uuid: str,
        characteristic: str,
        value: bytearray,
    ) -> bool:
        """Write to the GATT characteristic, returns whether it was written."""
        if not await self._ensure_client_connected() or (client := self.client) is None:
            return False

        try:
            char = self._get_characteristic(client, service_uuid, characteristic)
        except BleakCharacteristicNotFoundError:
            await self.async_disconnect()
            raise
        await client.write_gatt_char(
            char,
            value,
        )
        return True

    # -- hooks -----------------------------------------------------------

    async def _async_read_initial(self) -> None:
        """Read and subscribe to everything once, right after connecting."""
        raise NotImplementedError

    async def _async_refresh(self) -> None:
        """Re-read what a dropped notification would otherwise leave stale."""
        raise NotImplementedError

    async def _async_try_ensure_written_values(self) -> None:
        """Replay pending writes, dropping them when the device is off."""
        raise NotImplementedError

    def _on_disconnected(self) -> None:
        """Release anything tied to the connection (a poll task, for one)."""

    # -- commands: every family overrides the ones it can do -------------

    def _unsupported(self) -> UnsupportedCommandError:
        return UnsupportedCommandError(f"{self.family} cannot do this")

    async def async_set_heater(self, on: bool) -> bool:
        """Turn the heater on or off."""
        raise self._unsupported()

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the target temperature."""
        raise self._unsupported()

    async def async_set_fan(self, on: bool) -> bool:
        """Turn the pump on or off (Volcano)."""
        raise self._unsupported()

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Display in Celsius or Fahrenheit."""
        raise self._unsupported()

    async def async_set_display_on_cooling(self, on: bool) -> bool:
        """Keep the display on while cooling (Volcano)."""
        raise self._unsupported()

    async def async_set_vibration(self, on: bool) -> bool:
        """Enable or disable vibration."""
        raise self._unsupported()

    async def async_set_shut_off(self, minutes: int) -> bool:
        """Set the auto-off time in minutes (Volcano)."""
        raise self._unsupported()

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness (Volcano, Crafty)."""
        raise self._unsupported()

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset (Crafty, Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_superboost_temperature(self, offset: int) -> bool:
        """Set the superboost offset (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_auto_off_seconds(self, seconds: int) -> bool:
        """Set the auto-off time in seconds (Crafty)."""
        raise self._unsupported()

    async def async_set_charge_led(self, on: bool) -> bool:
        """Enable or disable the charge LED (Crafty)."""
        raise self._unsupported()

    async def async_set_auto_ble_shutdown(self, on: bool) -> bool:
        """Enable or disable automatic Bluetooth shutdown (Crafty)."""
        raise self._unsupported()

    async def async_find_device(self) -> bool:
        """Make the device signal so it can be found (Crafty+, Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_charge_optimization(self, on: bool) -> bool:
        """Enable or disable charge optimisation (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_charge_limit(self, on: bool) -> bool:
        """Enable or disable the charge limit (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_boost_visualization(self, on: bool) -> bool:
        """Show or hide boost on the display (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_boost_timeout_disabled(self, on: bool) -> bool:
        """Disable or enable the boost timeout (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Keep Bluetooth on while asleep (Veazy)."""
        raise self._unsupported()

    async def async_set_brightness(self, brightness: int) -> bool:
        """Set the display brightness 1-9 (Venty, Veazy)."""
        raise self._unsupported()
