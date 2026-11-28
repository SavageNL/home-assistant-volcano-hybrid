"""Data class for the Volcano Hybrid device."""

from __future__ import annotations

from .const import (
    FAMILY_MODEL_NAME,
    VOLCANO_HYBRID_DISPLAY_OFF_TEMP,
    VOLCANO_HYBRID_MAX_TEMP,
    VOLCANO_HYBRID_MIN_TEMP,
    DeviceFamily,
    VolcanoSensor,
)
from .data import DeviceData, TrackedValue, VolcanoHybridDataStatusProvider
from .fault_log import FAULT_NONE, decode_fault_log

__all__ = [
    "VolcanoHybridData",
    "VolcanoHybridDataStatusProvider",
]


class VolcanoHybridData(DeviceData):
    """Data object to hold Volcano Hybrid data."""

    family = DeviceFamily.VOLCANO_HYBRID
    MIN_TEMP = VOLCANO_HYBRID_MIN_TEMP
    MAX_TEMP = VOLCANO_HYBRID_MAX_TEMP
    MAX_READING = VOLCANO_HYBRID_MAX_TEMP
    MIN_DISPLAY_TEMP = 40
    capabilities = frozenset(
        {
            VolcanoSensor.VOLCANO,
            VolcanoSensor.FIRMWARE,
            VolcanoSensor.CURRENT_AUTO_OFF_TIME,
            VolcanoSensor.CURRENT_ON_TIME,
            VolcanoSensor.HEAT_TIME,
            VolcanoSensor.SHUT_OFF,
            VolcanoSensor.LED_BRIGHTNESS,
            VolcanoSensor.AUTO_SHUTDOWN,
            VolcanoSensor.AT_TEMPERATURE,
            VolcanoSensor.HEATER_ACTIVE,
            VolcanoSensor.PUMP_ACTIVE,
            VolcanoSensor.ACTUATOR_FAULT,
            VolcanoSensor.PRV1_ERROR,
            VolcanoSensor.SHOWING_CELSIUS,
            VolcanoSensor.DISPLAY_ON_COOLING,
            VolcanoSensor.SERVICE_MODE,
            VolcanoSensor.PRV2_ERROR,
            VolcanoSensor.VIBRATION,
            VolcanoSensor.RECONNECT,
            VolcanoSensor.DELAYED_RECONNECT,
            VolcanoSensor.AUTO_CONNECT,
            VolcanoSensor.CONNECTED,
            VolcanoSensor.RSSI,
            VolcanoSensor.CONNECTED_ADDR,
            VolcanoSensor.MAINS_VOLTAGE,
            VolcanoSensor.PRJ1,
            VolcanoSensor.PRJ2,
            VolcanoSensor.PRJ3,
            VolcanoSensor.PRJ4,
            VolcanoSensor.PRJ5,
            VolcanoSensor.HIST1,
            VolcanoSensor.HIST2,
            VolcanoSensor.LAST_FAULT,
        }
    )

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the Volcano Hybrid data object."""
        super().__init__(device)

        # What the device calls itself ("HYBRID") and the mains it was built
        # for ("230VAC"). Both are fixed identity strings, and both stay None on
        # a device whose BLE module does not serve them.
        self.model: str | None = None
        self.mains_voltage: str | None = None
        self.firmware: str | None = None
        self._current_auto_off_time: float | None = None
        self._heat_hours: int | None = None
        self._heat_minutes: int | None = None
        # The lifetime hours and minutes notify separately, so at every full
        # hour one arrives before the other (see heat_time).
        self._hour_carry_pending = False
        self._minute_wrap_pending = False
        # The hours as they were when the minutes last changed: a minutes drop
        # only means a wrap if the hours have not moved since.
        self._hours_at_last_minutes: int | None = None
        self.shut_off: int | None = None
        self.led_brightness: int | None = None

        # Raw status registers and error history, kept purely for diagnostics.
        # The vendor app reads prj1-3 and both histories when building the
        # report it asks users to send to support. prj4 and prj5 are the two
        # remaining controller status words, which nothing decodes yet and
        # which no device has been seen serving, so they stay None whenever the
        # device does not offer them.
        self.prj1: int | None = None
        self.prj2: int | None = None
        self.prj3: int | None = None
        self.prj4: int | None = None
        self.prj5: int | None = None
        self.hist1: str | None = None
        self.hist2: str | None = None

        # Prv1 attributes
        self._fan: TrackedValue[bool] = TrackedValue()
        self._tracked.append(self._fan)
        self.auto_shutdown: bool | None = None
        self.actuator_fault: bool | None = None
        self.prv1_error: bool | None = None

        # Prv2 attributes
        self.showing_celsius: bool | None = None
        self.display_on_cooling: bool | None = None
        self.service_mode: bool | None = None
        self.prv2_error: bool | None = None

        # Prv3 attributes
        self.vibration: bool | None = None

    @property
    def model_name(self) -> str:
        """
        Render the model the device reports as the name people know it by.

        The device answers a bare product class — `HYBRID` on the unit this was
        read from, and the firmware seeds that from a model class that also has a
        Medic variant. Shown verbatim it would replace the "Volcano Hybrid" the
        device registry has always displayed with a shoutier version of the same
        fact, so the class is titled and prefixed instead: `HYBRID` renders exactly
        what was there before, while a different class still reads correctly.
        Anything that is not a plain word is left alone rather than dressed up.
        """
        if not self.model or not self.model.isalpha():
            return FAMILY_MODEL_NAME[self.family]
        return f"Volcano {self.model.capitalize()}"

    @property
    def is_on(self) -> bool:
        """Check if the device is on."""
        return bool(self.fan or self.heater)

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

    @property
    def hist1_faults(self) -> list[dict[str, str]]:
        """The faults the first history characteristic spells out."""
        return decode_fault_log(self.hist1)

    @property
    def hist2_faults(self) -> list[dict[str, str]]:
        """The faults the second history characteristic spells out."""
        return decode_fault_log(self.hist2)

    @property
    def last_fault(self) -> str | None:
        """
        The most recently logged fault, as a translation key.

        Taken from the first history characteristic, which is the one that
        answered with codes on the device this was read from. Which of the two
        holds the ring of codes and which the per-code counters is still open
        (VOLCANO_BLE_SPEC.md §7), so both are decoded and neither is labelled;
        this only reports the first entry of the one that looked like a log.

        None until the log has actually been read, so a device that has not
        been connected to reads as unknown rather than claiming a clean record.
        """
        if self.hist1 is None:
            return None
        faults = self.hist1_faults
        return faults[0]["fault"] if faults else FAULT_NONE

    @property
    def fan_write(self) -> bool | None:
        """Return the pending fan write."""
        return self._fan.pending

    @fan_write.setter
    def fan_write(self, value: bool | None) -> None:
        self._fan.pending = value

    def discard_fan_write(self, value: bool) -> None:
        """Forget a fan write that was never sent."""
        self._fan.discard(value)

    @property
    def fan_state(self) -> bool | None:
        """Return the fan as it should be shown."""
        return self._fan.state

    @property
    def fan(self) -> bool | None:
        """Return the confirmed fan state."""
        return self._fan.value

    @fan.setter
    def fan(self, value: bool) -> None:
        self._fan.value = value

    @property
    def fan_needs_write(self) -> bool:
        """Check if the fan needs to be written."""
        return self._fan.needs_write

    @property
    def heat_hours_changed(self) -> int | None:
        """Lifetime heater hours, as the device last reported them."""
        return self._heat_hours

    @heat_hours_changed.setter
    def heat_hours_changed(self, hours: int | None) -> None:
        previous = self._heat_hours
        self._heat_hours = hours
        if self._hour_carry_pending:
            # The minutes already wrapped; this is the hour that goes with it.
            self._hour_carry_pending = False
        elif previous is not None and hours == previous + 1:
            # The hour ticked first; the minutes' wrap to 0 has yet to arrive.
            self._minute_wrap_pending = True

    @property
    def heat_minutes_changed(self) -> int | None:
        """Lifetime heater minutes past the hour, as last reported."""
        return self._heat_minutes

    @heat_minutes_changed.setter
    def heat_minutes_changed(self, minutes: int | None) -> None:
        previous = self._heat_minutes
        hours_unchanged = self._hours_at_last_minutes == self._heat_hours
        self._heat_minutes = minutes
        self._hours_at_last_minutes = self._heat_hours
        if self._minute_wrap_pending:
            self._minute_wrap_pending = False
        elif (
            previous is not None
            and minutes is not None
            and minutes < previous
            and hours_unchanged
        ):
            # The minutes wrapped first; the hour's increment is on its way.
            # With the hours already moved on (a reconnect after hours of use
            # elsewhere), the drop is just the new reading and nothing is due.
            self._hour_carry_pending = True

    @property
    def heat_time(self) -> int | None:
        """
        Lifetime heating time in minutes.

        `hours * 60 + minutes` (spec §2), corrected for the moment between the
        two notifications at a full hour. Read naively, a device that sends
        the minutes' wrap first reports 1458:59 → 1458:00 → 1459:00, and a
        `total_increasing` sensor that drops is taken for a meter reset.
        Whichever half arrives first, the other is assumed until it follows.
        """
        hours, minutes = self._heat_hours, self._heat_minutes
        if hours is None or minutes is None:
            return None
        if self._hour_carry_pending:
            hours += 1
        if self._minute_wrap_pending:
            minutes = 0
        return hours * 60 + minutes

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
        """
        Get the current on time in minutes.

        None when the countdown exceeds the setting: the countdown is only
        loaded when an actuator switches on and nothing else reloads it
        (VOLCANO_BLE_SPEC.md §2, STRONG), so lowering the auto-off setting
        mid-session leaves an on time that cannot be derived, not a negative
        one.
        """
        if self.shut_off is None or self.current_auto_off_time is None:
            return None
        on_time = self.shut_off - self.current_auto_off_time
        return on_time if on_time >= 0 else None
