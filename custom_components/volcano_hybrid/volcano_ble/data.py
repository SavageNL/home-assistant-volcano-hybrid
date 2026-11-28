"""State shared by every Storz & Bickel device, and how pending writes are tracked."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from .const import FAMILY_MODEL_NAME, DeviceFamily

T = TypeVar("T")


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


class TrackedValue(Generic[T]):  # noqa: UP046
    """
    A device value together with the last write not yet confirmed for it.

    The write is recorded *before* it is sent, because the device's confirming
    notification can arrive before the GATT write call returns
    (VOLCANO_BLE_SPEC.md §5). A write that matches what the device already
    reports is dropped on the spot so it can never be replayed later.
    """

    def __init__(self) -> None:
        """Start with nothing read and nothing pending."""
        self._value: T | None = None
        self._pending: T | None = None

    @property
    def value(self) -> T | None:
        """The value the device last confirmed."""
        return self._value

    @value.setter
    def value(self, value: T | None) -> None:
        self._value = value
        if self._pending is not None and self._pending == value:
            self._pending = None

    @property
    def pending(self) -> T | None:
        """The write still waiting for the device to confirm it."""
        return self._pending

    @pending.setter
    def pending(self, value: T | None) -> None:
        self._pending = None if value == self._value else value

    @property
    def state(self) -> T | None:
        """What the entity should show: the pending write, else the value."""
        return self._pending if self._pending is not None else self._value

    @property
    def needs_write(self) -> bool:
        """Whether a pending write still has to be (re)sent."""
        return self._pending is not None and self._pending != self._value

    def clear(self) -> None:
        """Drop the pending write."""
        self._pending = None

    def discard(self, value: T) -> None:
        """
        Drop the pending write if it is still `value`.

        For a write that was never sent. Compared first so that a newer command
        recorded while this one was failing is kept.
        """
        if self._pending == value:
            self._pending = None


class DeviceData:
    """What every family reports: temperatures, the heater, identity."""

    family: DeviceFamily
    # The entity keys (VolcanoSensor values) the family supports. Static per
    # family: what a device cannot do fails with `not_supported` rather than
    # changing the entity set after setup.
    capabilities: frozenset[str] = frozenset()
    MIN_TEMP = 0
    MAX_TEMP = 230
    # The highest current temperature accepted as a reading; above it the
    # device is taken to have no reading. Separate from MAX_TEMP, the top of
    # the target range, which a portable device's boost can overshoot.
    MAX_READING = 230
    MIN_DISPLAY_TEMP = 40

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the shared fields."""
        self.device = device
        self._current_temp: int | None = None
        self._set_temp: TrackedValue[int] = TrackedValue()
        self._heater: TrackedValue[bool] = TrackedValue()
        self._tracked: list[TrackedValue[Any]] = [self._set_temp, self._heater]

        self.serial_number: str | None = None
        self.firmware_version: str | None = None
        self.firmware_ble_version: str | None = None
        self.bootloader_version: str | None = None
        # The device's own "setpoint reached" signal.
        self.at_temperature: bool | None = None

    # -- identity --------------------------------------------------------

    @property
    def model_name(self) -> str:
        """The model to show in the device registry."""
        return FAMILY_MODEL_NAME[self.family]

    # -- derived state ---------------------------------------------------

    @property
    def is_assumed(self) -> bool:
        """Whether any write is still waiting for confirmation."""
        return any(tracked.needs_write for tracked in self._tracked)

    @property
    def is_on(self) -> bool:
        """Whether the device is doing anything."""
        return bool(self.heater)

    @property
    def is_heating(self) -> bool | None:
        """
        Whether the heater is working towards a setpoint it has not reached.

        The device has no signal for its heating element: PRJSTAT1 does not
        change at all while it holds temperature, and its "setpoint reached"
        bit is a latch that only clears when the target is raised 3 °C or more
        above the *previous target* — never against the current reading, and
        never when the target is lowered — so it keeps claiming to be at
        temperature through small adjustments and all the way down a coast.
        Comparing the two temperatures the device does report is finer grained
        and works in both directions.
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
        """Whether the device is still cooling down; only the Volcano infers this."""
        return False

    def clear_open_writes(self) -> None:
        """Remove all open writes."""
        for tracked in self._tracked:
            tracked.clear()

    # -- temperatures ----------------------------------------------------

    @property
    def current_temp(self) -> int | None:
        """Get the current temp."""
        if self._current_temp is not None and self._current_temp > 0:
            return self._current_temp
        return None

    @current_temp.setter
    def current_temp(self, value: int) -> None:
        if self.MIN_TEMP <= value <= self.MAX_READING:
            self._current_temp = value
        else:
            self._current_temp = None

    @property
    def set_temp(self) -> int | None:
        """Return the confirmed target temperature."""
        return self._set_temp.value

    @set_temp.setter
    def set_temp(self, value: int) -> None:
        self._set_temp.value = value

    @property
    def set_temp_write(self) -> int | None:
        """Return the pending target write."""
        return self._set_temp.pending

    @set_temp_write.setter
    def set_temp_write(self, value: int | None) -> None:
        self._set_temp.pending = value

    def discard_set_temp_write(self, value: int) -> None:
        """Forget a target write that was never sent."""
        self._set_temp.discard(value)

    @property
    def set_temp_state(self) -> int | None:
        """Return the target as it should be shown."""
        return self._set_temp.state

    @property
    def set_temp_needs_write(self) -> bool:
        """Check if the target needs to be written."""
        return self._set_temp.needs_write

    # -- heater ----------------------------------------------------------

    @property
    def heater(self) -> bool | None:
        """Return the confirmed heater state."""
        return self._heater.value

    @heater.setter
    def heater(self, value: bool) -> None:
        self._heater.value = value

    @property
    def heater_write(self) -> bool | None:
        """Return the pending heater write."""
        return self._heater.pending

    @heater_write.setter
    def heater_write(self, value: bool | None) -> None:
        self._heater.pending = value

    def discard_heater_write(self, value: bool) -> None:
        """Forget a heater write that was never sent."""
        self._heater.discard(value)

    @property
    def heater_state(self) -> bool | None:
        """Return the heater state as it should be shown."""
        return self._heater.state

    @property
    def heater_needs_write(self) -> bool:
        """Check if the heater needs to be written."""
        return self._heater.needs_write

    # -- connection ------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the device is connected."""
        return self.device.is_connected

    @property
    def rssi(self) -> int | None:
        """The current rssi."""
        return self.device.rssi

    @property
    def connected_addr(self) -> str | None:
        """The adapter the device is connected through."""
        return self.device.connected_addr

    def get(self, key: str) -> Any | None:
        """Get the value of the specified key."""
        return getattr(self, key)
