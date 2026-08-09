"""Data class for the Volcano Hybrid device."""

from __future__ import annotations

from typing import Any

from .const import (
    VOLCANO_HYBRID_DISPLAY_OFF_TEMP,
    VOLCANO_HYBRID_MAX_TEMP,
    VOLCANO_HYBRID_MIN_TEMP,
)


class VolcanoHybridDataStatusProvider:
    """Interface to retrieve Device data from the Data."""

    @property
    def rssi(self) -> int | None:
        """Get the device rssi."""
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        """Determine whether the device is connected."""
        raise NotImplementedError

    @property
    def connected_addr(self) -> str | None:
        """Get the connected mac address."""
        raise NotImplementedError


class VolcanoHybridData:
    """Data object to hold Volcano Hybrid data."""

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the Volcano Hybrid data object."""
        self.device = device
        self._current_temp: int | None = None
        self._set_temp: int | None = None

        self.serial_number: str | None = None
        self.firmware_version: str | None = None
        self.firmware_ble_version: str | None = None
        self.bootloader_version: str | None = None
        self.firmware: str | None = None
        self._current_auto_off_time: float | None = None
        self.heat_hours_changed: int | None = None
        self.heat_minutes_changed: int | None = None
        self.shut_off: int | None = None
        self.led_brightness: int | None = None

        # Raw status registers and error history, kept purely for diagnostics.
        # The vendor app reads exactly these five when building the report it
        # asks users to send to support.
        self.prj1: int | None = None
        self.prj2: int | None = None
        self.prj3: int | None = None
        self.hist1: str | None = None
        self.hist2: str | None = None

        # Prv1 attributes
        self._heater: bool | None = None
        self._fan: bool | None = None
        self.auto_shutdown: bool | None = None
        # The device's own "setpoint reached" signal, so nothing has to compare
        # the current temperature against the target to know it is ready.
        self.at_temperature: bool | None = None
        self.actuator_fault: bool | None = None
        self.prv1_error: bool | None = None

        # Prv2 attributes
        self.showing_celsius: bool | None = None
        self.display_on_cooling: bool | None = None
        self.prv2_error: bool | None = None

        # Prv3 attributes
        self.vibration: bool | None = None

        # Attributes that will be set frequently and which we want to track being set
        self._set_temp_write: int | None = None
        self._heater_write: bool | None = None
        self._fan_write: bool | None = None

    @property
    def is_assumed(self) -> bool:
        """Checks if the value and value_write's are the same."""
        return (
            (self.set_temp_write is not None and self.set_temp != self.set_temp_write)
            or (self.heater_write is not None and self.heater != self.heater_write)
            or (self.fan_write is not None and self.fan != self.fan_write)
        )

    @property
    def is_on(self) -> bool:
        """Check if the device is on."""
        return bool(self.fan or self.heater)

    @property
    def is_heating(self) -> bool | None:
        """
        Whether the heater is working towards a setpoint it has not reached.

        The device has no signal for its heating element: PRJSTAT1 does not
        change at all while it holds temperature, and its "setpoint reached"
        bit only clears once the setpoint moves more than two degrees above
        the current reading, so it keeps claiming to be at temperature through
        small adjustments. Comparing the two temperatures the device does
        report is finer grained and works in both directions.
        """
        heater = self.heater_state
        if heater is None:
            return None
        if not heater:
            return False
        if self.current_temp is None or self.set_temp_state is None:
            return None
        return self.current_temp < self.set_temp_state

    @property
    def is_cooling(self) -> bool:
        """
        Whether the heater is off but the device is still cooling down, lit.

        This one is inferred rather than read. PRJSTAT1 reads all zeroes the
        instant the heater is switched off, however hot the block still is, so
        the only things left to go on are the temperature the device keeps
        reporting and the setting deciding whether its display stays on for it.
        """
        if self.heater_state is not False or not self.display_on_cooling:
            return False
        if self.current_temp is None:
            return False
        return self.current_temp >= VOLCANO_HYBRID_DISPLAY_OFF_TEMP

    def clear_open_writes(self) -> None:
        """Remove all open writes."""
        self.heater_write = None
        self.fan_write = None
        self.set_temp_write = None

    @property
    def fan_write(self) -> bool | None:
        """Return the pending fan write."""
        return self._fan_write

    @fan_write.setter
    def fan_write(self, value: bool | None) -> None:
        """Set the pending fan write, dropping it when already confirmed."""
        self._fan_write = None if value == self._fan else value

    @property
    def heater_write(self) -> bool | None:
        """Return the pending heater write."""
        return self._heater_write

    @heater_write.setter
    def heater_write(self, value: bool | None) -> None:
        """Set the pending heater write, dropping it when already confirmed."""
        self._heater_write = None if value == self._heater else value

    @property
    def set_temp_write(self) -> int | None:
        """Return the pending set_temp write."""
        return self._set_temp_write

    @set_temp_write.setter
    def set_temp_write(self, value: int | None) -> None:
        """Set the pending set_temp write, dropping it when already confirmed."""
        self._set_temp_write = None if value == self._set_temp else value

    @property
    def fan_state(self) -> bool | None:
        """
        Return the current fan state.

        Updated before actually confirmed to be written.
        """
        return self.fan_write if self.fan_write is not None else self.fan

    @property
    def fan(self) -> bool | None:
        """Return the current fan state."""
        return self._fan

    @fan.setter
    def fan(self, value: bool) -> None:
        """Set the current fan state (and clears the write if they match)."""
        self._fan = value
        if self.fan_write is not None and self.fan == self.fan_write:
            self.fan_write = None

    @property
    def fan_needs_write(self) -> bool:
        """Check if the fan needs to be written."""
        return self.fan_write is not None and self.fan != self.fan_write

    @property
    def heater_state(self) -> bool | None:
        """
        Return the current heater state.

        Updated before actually confirmed to be written.
        """
        return self.heater_write if self.heater_write is not None else self.heater

    @property
    def heater(self) -> bool | None:
        """Returns the current heater state."""
        return self._heater

    @heater.setter
    def heater(self, value: bool) -> None:
        """Set the current heater state (and clears the write if they match)."""
        self._heater = value
        if self.heater_write is not None and self.heater == self.heater_write:
            self.heater_write = None

    @property
    def heater_needs_write(self) -> bool:
        """Check if the heater needs to be written."""
        return self.heater_write is not None and self.heater != self.heater_write

    @property
    def set_temp_state(self) -> int | None:
        """
        Return the current set_temp state.

        updated before actually confirmed to be written.
        """
        return self.set_temp_write if self.set_temp_write is not None else self.set_temp

    @property
    def set_temp(self) -> int | None:
        """Return the current set_temp state."""
        return self._set_temp

    @set_temp.setter
    def set_temp(self, value: int) -> None:
        """Set the current set_temp state (and clears the write if they match)."""
        self._set_temp = value
        if self.set_temp_write is not None and self.set_temp == self.set_temp_write:
            self.set_temp_write = None

    @property
    def set_temp_needs_write(self) -> bool:
        """Check if the set_temp needs to be written."""
        return self.set_temp_write is not None and self.set_temp != self.set_temp_write

    @property
    def connected(self) -> bool:
        """Get the current auto off time in minutes."""
        return self.device.is_connected

    @property
    def rssi(self) -> int | None:
        """The current rssi."""
        return self.device.rssi

    @property
    def connected_addr(self) -> str | None:
        """The current rssi."""
        return self.device.connected_addr

    @property
    def heat_time(self) -> int | None:
        """Get the current auto off time in minutes."""
        if self.heat_hours_changed is None or self.heat_minutes_changed is None:
            return None
        return self.heat_hours_changed * 60 + self.heat_minutes_changed

    @property
    def current_auto_off_time(self) -> float | None:
        """Get the current auto off time in minutes."""
        if self._current_auto_off_time and self._current_auto_off_time > 0:
            return self._current_auto_off_time
        return None

    @current_auto_off_time.setter
    def current_auto_off_time(self, value: float) -> None:
        self._current_auto_off_time = value

    @property
    def current_on_time(self) -> float | None:
        """Get the current on time in minutes."""
        if self.shut_off is None or self.current_auto_off_time is None:
            return None
        return self.shut_off - self.current_auto_off_time

    @property
    def current_temp(self) -> int | None:
        """Get the current temp."""
        if self._current_temp is not None and self._current_temp > 0:
            return self._current_temp
        return None

    @current_temp.setter
    def current_temp(self, value: int) -> None:
        if VOLCANO_HYBRID_MIN_TEMP <= value <= VOLCANO_HYBRID_MAX_TEMP:
            self._current_temp = value
        else:
            self._current_temp = None

    def get(self, key: str) -> Any | None:
        """Get the value of the specified key."""
        return getattr(self, key)
