"""Data class for the Volcano Hybrid device."""

from __future__ import annotations

from typing import Any


class VolcanoHybridDataStatusProvider:
    """Interface to retrieve Device data from the Data."""

    @property
    def rssi(self) -> int:
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
        self._current_auto_off_time: int | None = None
        self.heat_hours_changed: int | None = None
        self.heat_minutes_changed: int | None = None
        self.shut_off: int | None = None
        self.led_brightness: int | None = None

        # Prv1 attributes
        self._heater: bool | None = None
        self._fan: bool | None = None
        self.auto_shutdown: bool | None = None
        self.prv1_error: bool | None = None

        # Prv2 attributes
        self.showing_celsius: bool | None = None
        self.display_on_cooling: bool | None = None
        self.prv2_error: bool | None = None

        # Prv3 attributes
        self.vibration: bool | None = None

        # Attributes that will be set frequently and which we want to track being set
        self.set_temp_write: int | None = None
        self.heater_write: bool | None = None
        self.fan_write: bool | None = None

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
        return self.fan or self.heater

    def clear_open_writes(self) -> None:
        """Remove all open writes."""
        self.heater_write = None
        self.fan_write = None
        self.set_temp_write = None

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
    def set_temp(self) -> bool | None:
        """Return the current set_temp state."""
        return self._set_temp

    @set_temp.setter
    def set_temp(self, value: bool) -> None:
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
    def rssi(self) -> int:
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
    def current_auto_off_time(self) -> int | None:
        """Get the current auto off time in minutes."""
        if self._current_auto_off_time and self._current_auto_off_time > 0:
            return self._current_auto_off_time
        return None

    @property
    def current_on_time(self) -> int | None:
        """Get the current auto off time in minutes."""
        if self.current_auto_off_time:
            return self.shut_off - self.current_auto_off_time
        return None

    @current_auto_off_time.setter
    def current_auto_off_time(self, value: int) -> None:
        self._current_auto_off_time = value
        
    @property
    def current_temp(self) -> int | None:
        """Get the current temp."""
        if (self._current_temp is not None and 
            self._current_temp > 0 and 
            self._current_temp <= 500 and  # Reasonable upper limit
            (self.heater or self._current_temp > 10)):  # Only trust readings when heater is on or temp is reasonable
            return self._current_temp
        return None

    @current_temp.setter
    def current_temp(self, value: int) -> None:
        self._current_temp = value

    def get(self, key: str) -> Any | None:
        """Get the value of the specified key."""
        return getattr(self, key)
