"""Coordinator for Volcano Hybrid BLE device."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakError
from habluetooth import BluetoothScanningMode
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothChange
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTO_CONNECT_DELAY,
    CONF_DELAYED_RECONNECT_DELAY,
    DEFAULT_AUTO_CONNECT_DELAY,
    DEFAULT_DELAYED_RECONNECT_DELAY,
    DOMAIN,
)
from .volcano_ble import (
    CommandNotConfirmedError,
    DeviceData,
    DeviceFamily,
    StorzBickelDevice,
    UnsupportedCommandError,
    create_device,
)
from .volcano_ble.const import FAMILY_MODEL_NAME

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# A conversion from another unit lands at least 1/18 °C away from a whole
# degree; anything closer is float noise from converting a whole °C back.
_TARGET_NOISE = 0.01


def whole_degree_target(target: float, current: int | None) -> int:
    """
    Round a requested target to the whole °C the device stores.

    Home Assistant converts a target set in °F to °C before it gets here, and
    steps it by the entity's 1° step in the *displayed* unit. One °F is only
    5/9 °C, so rounding to the nearest degree can land back on the current
    target: from 186 °C (shown as 367 °F) a step down asks for 366 °F, which is
    185.56 °C and rounds to 186 again, so the button seems dead. A request that
    rounds onto the current target but plainly asks to move goes one degree
    in the direction asked instead.
    """
    nearest = math.floor(target + 0.5)
    if current is None or nearest != current or abs(target - current) < _TARGET_NOISE:
        return nearest
    return current + 1 if target > current else current - 1


class TemperatureWaitError(Exception):
    """A wait for the target temperature ended without reaching it."""

    def __init__(self, reason: str) -> None:
        """Record why the wait ended, as one of the WAIT_* reasons."""
        super().__init__(reason)
        self.reason = reason


WAIT_TIMEOUT = "timeout"
WAIT_DISCONNECTED = "disconnected"
WAIT_HEATER_OFF = "heater_off"
WAIT_TARGET_CHANGED = "target_changed"

# How long a condition has to last before it ends a wait, in seconds. A Volcano
# switching on often reports its heater off for up to a few seconds, some
# 25-40 s in; and a connection can drop for 5-10 s while the device carries on
# heating. Neither lasts as long as its grace; a real switch-off or a lost
# device does.
WAIT_GRACE = {
    WAIT_HEATER_OFF: 15.0,
    WAIT_DISCONNECTED: 30.0,
}

type VolcanoHybridConfigEntry = ConfigEntry[VolcanoHybridCoordinator]


class VolcanoHybridCoordinator(DataUpdateCoordinator[DeviceData]):
    """Coordinator that maintains the BLE connection and pushes device updates."""

    config_entry: VolcanoHybridConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: VolcanoHybridConfigEntry,
        address: str,
        family: DeviceFamily,
    ) -> None:
        """Initialize the coordinator."""
        self.family = family
        model = FAMILY_MODEL_NAME[family]
        super().__init__(
            hass,
            _LOGGER,
            name=model,
            config_entry=config_entry,
            update_interval=timedelta(seconds=10),
            always_update=True,
        )

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=model,
            manufacturer="Storz & Bickel",
            model=model,
            connections={(CONNECTION_BLUETOOTH, address)},
        )
        self._device: StorzBickelDevice = create_device(
            family, self.async_update_listeners, self.update_device
        )
        self.data = self._device.data
        self.address = address
        self._was_connected = False
        # Whether the integration may connect on its own. Disabling this frees
        # the device so other Bluetooth clients can use it; commands and the
        # manual reconnect buttons still connect on demand.
        self.auto_connect = True
        self._connect_timer: CALLBACK_TYPE | None = None

    @property
    def auto_connect_delay(self) -> float:
        """Seconds to wait before auto-connecting after seeing the device."""
        return float(
            self.config_entry.options.get(
                CONF_AUTO_CONNECT_DELAY, DEFAULT_AUTO_CONNECT_DELAY
            )
        )

    @property
    def delayed_reconnect_delay(self) -> float:
        """Seconds the delayed reconnect button stays disconnected."""
        return float(
            self.config_entry.options.get(
                CONF_DELAYED_RECONNECT_DELAY, DEFAULT_DELAYED_RECONNECT_DELAY
            )
        )

    async def async_register_callbacks(self) -> None:
        """
        Install the advertisement callback without connecting.

        Called from setup instead of ``async_config_entry_first_refresh`` so a
        slow cold-boot connect never blocks Home Assistant startup; the first
        connect runs in a background task. (Newer HA exposes a public
        ``async_setup`` wrapper for the ``_async_setup`` hook, but the pinned
        version does not, so the hook is invoked directly here.)
        """
        await self._async_setup()

    async def _async_setup(self) -> None:
        """Register the advertisement callback that drives auto-connect."""

        @callback
        def _on_advertisement(
            service_info: BluetoothServiceInfoBleak, _: BluetoothChange
        ) -> None:
            # Reflect the live signal, then schedule a connect. Scheduling
            # (rather than connecting on this advertisement) collapses a
            # power-on burst into one attempt and gives every Bluetooth proxy
            # a moment to report so the best path is chosen.
            # Assigning the property (not the backing field) pushes the new
            # signal strength to the entities right away, so the RSSI sensor
            # tracks advertisements instead of only the 10s fallback poll.
            self._device.rssi = service_info.rssi
            if self.auto_connect and not self._device.is_connected:
                self._schedule_connect(self.auto_connect_delay)

        self.config_entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                _on_advertisement,
                BluetoothCallbackMatcher(connectable=True, address=self.address),
                BluetoothScanningMode.ACTIVE,
            )
        )
        # Make sure a scheduled connect never outlives the entry.
        self.config_entry.async_on_unload(self._cancel_connect_timer)

    @callback
    def _schedule_connect(self, delay: float, *, force: bool = False) -> None:
        """
        Schedule a single connect attempt after a delay.

        A non-forced call is a no-op while one is already pending, so an
        advertisement burst results in only one attempt. A forced call
        (manual reconnect) replaces any pending attempt and ignores the
        auto-connect setting.
        """
        if force:
            self._cancel_connect_timer()
        elif self._connect_timer is not None:
            return

        @callback
        def _connect(_now: datetime) -> None:
            self._connect_timer = None
            if not force and (not self.auto_connect or self._device.is_connected):
                return
            # An entry background task, so unloading the entry cancels a
            # connect still in flight; otherwise it could finish after the
            # shutdown's disconnect and leave a connection nothing owns.
            self.config_entry.async_create_background_task(
                self.hass,
                self._async_refresh_device(connect=True),
                f"{DOMAIN}_connect",
            )

        self._connect_timer = async_call_later(self.hass, delay, _connect)

    @callback
    def _cancel_connect_timer(self) -> None:
        """Cancel a pending scheduled connect, if any."""
        if self._connect_timer is not None:
            self._connect_timer()
            self._connect_timer = None

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        self._cancel_connect_timer()
        # The base marks the coordinator shut down, so a refresh after unload
        # no longer reaches the device (and, with auto-connect on, reconnects).
        await super().async_shutdown()
        await self._device.async_disconnect()

    async def _async_update_data(self) -> DeviceData:
        """Reconnect/refresh on the coordinator interval (a fallback poll)."""
        try:
            await self._async_refresh_device(connect=self.auto_connect)
        except BleakError as err:
            # A failed read is routine over a Bluetooth proxy (GATT error 133,
            # say) and the next poll usually succeeds. As UpdateFailed it is
            # one log line instead of an "unexpected error" traceback, and
            # async_update_listeners keeps a still-connected device available.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return self._device.data

    async def _async_refresh_device(self, *, connect: bool) -> None:
        """Refresh the device, optionally (re)connecting to it."""
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, True)

        last_info = bluetooth.async_last_service_info(self.hass, self.address)
        if last_info:
            self._device.device_rssi = last_info.rssi

        # An established connection is enough to refresh over. The vaporizer
        # stops advertising once something is connected to it, so it drops out
        # of the Bluetooth address cache and ``device`` becomes None; requiring
        # one here silently skipped every poll for as long as the connection
        # lasted. That left the current temperature to its notifications alone,
        # frozen on the last one that arrived, and never replayed a pending
        # write. Only a connect still needs a device to connect to.
        if self._device.is_connected or (device and connect):
            await self._device.async_manual_update(device)

    def async_update_listeners(self) -> None:
        """Update listeners."""
        connected = self._device.is_connected
        if connected != self._was_connected:
            if connected:
                _LOGGER.info("Connected to the %s at %s", self.name, self.address)
            else:
                _LOGGER.info("Connection to the %s at %s lost", self.name, self.address)
            self._was_connected = connected
        self.last_update_success = connected
        super().async_update_listeners()

    def update_device(self) -> None:
        """Update the device registry with the latest data."""
        # The device names its own model, so use that once it has been read.
        # device_info is kept in step with the registry so entities added after
        # this point describe the same device; its identifiers are deliberately
        # untouched, since they are what the device is keyed by and every
        # entity's unique id is derived from the address alongside them.
        model = self.data.model_name
        self.device_info["model"] = model

        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(self.device_info.get("identifiers"))
        if not device:
            return

        dev_reg.async_update_device(
            device_id=device.id,
            model=model,
            serial_number=self.data.serial_number,
            sw_version=self.data.firmware_version,
            hw_version=self.data.bootloader_version,
        )

    async def _async_command(self, command: Awaitable[bool]) -> None:
        """Run a device command, raising HomeAssistantError when it fails."""
        try:
            written = await command
        except UnsupportedCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_supported",
            ) from err
        except CommandNotConfirmedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_confirmed",
            ) from err
        except BleakError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
            ) from err
        if not written:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
            )

    async def set_fan(self, on: bool) -> None:
        """Set the fan on or off."""
        await self._async_command(self._device.async_set_fan(on))

    async def set_heater(self, on: bool) -> None:
        """Set the heater on or off."""
        await self._async_command(self._device.async_set_heater(on))

    async def set_target_temperature(self, target: float) -> None:
        """Set the target temperature, rounded to a whole °C."""
        data = self.data
        whole = whole_degree_target(target, data.set_temp_state)
        whole = max(data.MIN_TEMP, min(data.MAX_TEMP, whole))
        await self._async_command(self._device.async_set_target_temperature(whole))

    async def async_wait_for_temperature(
        self, tolerance: float, max_wait: float
    ) -> None:
        """
        Wait until the current temperature reaches the target, less a tolerance.

        Raises TemperatureWaitError once the target can no longer be reached
        the way it was asked for: someone changes the target, or the heater is
        off or the device disconnected for longer than its WAIT_GRACE. A target
        below the current temperature counts as reached; this never waits for
        the device to cool down.
        """
        target = self.data.set_temp_state
        if target is None:
            raise TemperatureWaitError(WAIT_DISCONNECTED)
        loop = asyncio.get_running_loop()
        # When each blocking condition was first seen, so a short blip does not
        # end the wait: a heater that reads off for a second while it is
        # switching on, or a connection that drops and comes straight back.
        since: dict[str, float] = {}
        updated = asyncio.Event()
        remove_listener = self.async_add_listener(updated.set)
        try:
            async with asyncio.timeout(max_wait):
                while True:
                    updated.clear()
                    wake = self._wait_step(target, tolerance, since, loop.time())
                    if wake == 0:
                        return
                    try:
                        async with asyncio.timeout(wake):
                            await updated.wait()
                    except TimeoutError:
                        # A grace period ran out; the next step decides.
                        pass
        except TimeoutError as err:
            raise TemperatureWaitError(WAIT_TIMEOUT) from err
        finally:
            remove_listener()

    def _wait_step(
        self, target: int, tolerance: float, since: dict[str, float], now: float
    ) -> float | None:
        """
        Check the wait once.

        Returns 0 when the temperature is reached, otherwise how long to sleep
        at most before checking again (None: until the next update). Raises
        TemperatureWaitError once the target can no longer be reached.
        """
        data = self.data
        if data.set_temp_state not in (None, target):
            raise TemperatureWaitError(WAIT_TARGET_CHANGED)

        blocking = {
            WAIT_DISCONNECTED: not self._device.is_connected,
            WAIT_HEATER_OFF: data.heater_state is False,
        }
        wake: float | None = None
        for reason, active in blocking.items():
            if not active:
                since.pop(reason, None)
                continue
            remaining = WAIT_GRACE[reason] - (now - since.setdefault(reason, now))
            if remaining <= 0:
                raise TemperatureWaitError(reason)
            wake = remaining if wake is None else min(wake, remaining)
        if wake is not None:
            return wake

        current = data.current_temp
        return 0 if current is not None and current >= target - tolerance else None

    async def set_showing_celsius(self, on: bool) -> None:
        """Set the toggle for showing Celsius."""
        await self._async_command(self._device.async_set_showing_celsius(on))

    async def set_display_on_cooling(self, on: bool) -> None:
        """Set the toggle for display on cooling."""
        await self._async_command(self._device.async_set_display_on_cooling(on))

    async def set_vibration(self, on: bool) -> None:
        """Set the toggle for vibration."""
        await self._async_command(self._device.async_set_vibration(on))

    async def set_shut_off(self, minutes: float) -> None:
        """Set the shut off time in minutes."""
        await self._async_command(self._device.async_set_shut_off(int(minutes)))

    async def set_led_brightness(self, brightness: float) -> None:
        """Set the LED brightness."""
        await self._async_command(
            self._device.async_set_led_brightness(int(brightness))
        )

    async def set_boost_temp(self, offset: float) -> None:
        """Set the boost offset."""
        await self._async_command(self._device.async_set_boost_temperature(int(offset)))

    async def set_superboost_temp(self, offset: float) -> None:
        """Set the superboost offset."""
        await self._async_command(
            self._device.async_set_superboost_temperature(int(offset))
        )

    async def set_auto_off_seconds(self, seconds: float) -> None:
        """Set the auto-off time in seconds."""
        await self._async_command(self._device.async_set_auto_off_seconds(int(seconds)))

    async def set_charge_led(self, on: bool) -> None:
        """Enable or disable the charge LED."""
        await self._async_command(self._device.async_set_charge_led(on))

    async def find_device(self) -> None:
        """Make the device signal so it can be found."""
        await self._async_command(self._device.async_find_device())

    async def async_read_extended_diagnostics(self) -> dict[str, int | None]:
        """Read the device's undecoded extra values, for a diagnostics download."""
        return await self._device.async_read_extended_diagnostics()

    def gatt_table(self) -> dict[str, dict[str, list[str]]]:
        """Return the connected device's services, characteristics and properties."""
        return self._device.gatt_table()

    async def set_charge_optimization(self, on: bool) -> None:
        """Enable or disable charge optimisation."""
        await self._async_command(self._device.async_set_charge_optimization(on))

    async def set_charge_limit(self, on: bool) -> None:
        """Enable or disable the charge limit."""
        await self._async_command(self._device.async_set_charge_limit(on))

    async def set_boost_visualization(self, on: bool) -> None:
        """Show or hide boost on the display."""
        await self._async_command(self._device.async_set_boost_visualization(on))

    async def set_boost_timeout_disabled(self, on: bool) -> None:
        """Disable or re-enable the boost timeout."""
        await self._async_command(self._device.async_set_boost_timeout_disabled(on))

    async def set_permanent_bluetooth(self, on: bool) -> None:
        """Keep Bluetooth on while the device sleeps."""
        await self._async_command(self._device.async_set_permanent_bluetooth(on))

    async def set_brightness(self, brightness: float) -> None:
        """Set the display brightness 1-9."""
        await self._async_command(self._device.async_set_brightness(int(brightness)))

    async def reconnect(self) -> None:
        """Reconnect immediately, regardless of the auto-connect setting."""
        self._cancel_connect_timer()
        await self._device.async_disconnect()
        await self._async_refresh_device(connect=True)

    async def delayed_reconnect(self) -> None:
        """
        Disconnect, then reconnect after the configured delay.

        Staying disconnected lets the device advertise again so a better path
        can be picked, even when auto-connect is disabled.
        """
        await self._device.async_disconnect()
        self._schedule_connect(self.delayed_reconnect_delay, force=True)

    async def async_set_auto_connect(self, *, enabled: bool) -> None:
        """Enable or disable automatic connecting."""
        self.auto_connect = enabled
        if enabled:
            self._schedule_connect(self.auto_connect_delay)
        else:
            # Release the device so other Bluetooth clients can reach it.
            self._cancel_connect_timer()
            await self._device.async_disconnect()
        self.async_update_listeners()
