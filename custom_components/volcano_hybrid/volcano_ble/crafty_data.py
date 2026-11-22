"""State of a Crafty / Crafty+, and the pure decoders for it (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import re

from .const import (
    PORTABLE_MAX_READING,
    PORTABLE_MAX_TEMP,
    PORTABLE_MIN_DISPLAY_TEMP,
    PORTABLE_MIN_TEMP,
    DeviceFamily,
    VolcanoSensor,
)
from .data import DeviceData, VolcanoHybridDataStatusProvider

# PRJSTAT1 (spec §4.1)
MASK_PRJSTAT_CRAFTY_ACTIVE = 0x0010
MASK_PRJSTAT_BOOST_MODE_ENABLED = 0x0020
MASK_PRJSTAT_SUPERBOOST_MODE_ENABLED = 0x0040
MASK_PRJSTAT_ERROR = 0x2008
MASK_PRJSTAT_NEEDS_FACTORY_RESET = 0x8000
# PRJSTAT2 (spec §4.2) - bits 0 and 1 are *disable* bits
MASK_PRJSTAT2_DISABLE_VIBRATION = 0x0001
MASK_PRJSTAT2_DISABLE_CHARGELED = 0x0002
MASK_PRJSTAT2_SET_TEMP_REACHED = 0x0004
MASK_PRJSTAT2_FIND_DEVICE = 0x0008
# The vendor app calls this mask ENABLE_AUTOBLESHUTDOWN, but the toggle it drives
# is labelled "Permanent Bluetooth": set, the device keeps Bluetooth on (#108).
MASK_PRJSTAT2_PERMANENT_BLUETOOTH = 0x1000
# System / battery status words (spec §4.3): the app's "contact support" masks,
# each tested as "any bit set".
MASK_SYSTEM_ERROR = 0x0280
MASK_BATTERY1_ERROR = 0x0600
# Charger status (spec §4.4, SPECULATIVE): 0 unplugged, 2 charging; any other
# value is plugged in but not charging.
CHARGER_STATUS_CHARGING = 2

# Firmware generations (spec §6)
CRAFTY_SETTINGS_FIRMWARE = (2, 51)
CRAFTY_PLUS_MAJOR = 3
# The app reads a °C target as anything up to the 210 °C maximum; above that
# the device is set to °F and reports °F x10 over the same characteristic.
CRAFTY_MAX_CELSIUS = 210

_FIRMWARE = re.compile(r"^V?(\d{2})\.(\d{2})")


def decode_target(raw: int) -> int:
    """Turn a target reading (x10) into whole °C, converting a °F reading."""
    # A °F target between 104 and 210 °F is indistinguishable from °C (as in the app).
    target = round(raw / 10)
    if target > CRAFTY_MAX_CELSIUS:
        return round((target - 32) / 1.8)
    return target


def parse_crafty_firmware(version: str | None) -> tuple[int, int] | None:
    """Major/minor out of the `V02.51`-style string the Crafty serves."""
    if version is None or (match := _FIRMWARE.match(version)) is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


class CraftyData(DeviceData):
    """Data object for a Crafty or Crafty+."""

    family = DeviceFamily.CRAFTY
    MIN_TEMP = PORTABLE_MIN_TEMP
    MAX_TEMP = PORTABLE_MAX_TEMP
    MAX_READING = PORTABLE_MAX_READING
    MIN_DISPLAY_TEMP = PORTABLE_MIN_DISPLAY_TEMP
    capabilities = frozenset(
        {
            VolcanoSensor.VOLCANO,
            VolcanoSensor.BOOST_TEMP,
            VolcanoSensor.LED_BRIGHTNESS,
            VolcanoSensor.AUTO_OFF_SECONDS,
            VolcanoSensor.VIBRATION,
            VolcanoSensor.CHARGE_LED,
            VolcanoSensor.PERMANENT_BLUETOOTH,
            VolcanoSensor.AUTO_CONNECT,
            VolcanoSensor.BATTERY,
            VolcanoSensor.AUTO_OFF_COUNTDOWN,
            VolcanoSensor.HEAT_TIME,
            VolcanoSensor.RSSI,
            VolcanoSensor.CONNECTED_ADDR,
            VolcanoSensor.PRJ1,
            VolcanoSensor.PRJ2,
            VolcanoSensor.SYSTEM_STATUS,
            VolcanoSensor.BATTERY_STATUS1,
            VolcanoSensor.BATTERY_STATUS2,
            VolcanoSensor.AT_TEMPERATURE,
            VolcanoSensor.HEATER_ACTIVE,
            VolcanoSensor.BOOST_MODE,
            VolcanoSensor.SUPERBOOST_MODE,
            VolcanoSensor.ERROR,
            VolcanoSensor.NEEDS_FACTORY_RESET,
            VolcanoSensor.FIND_MODE,
            VolcanoSensor.CHARGING,
            VolcanoSensor.BATTERY_CURRENT,
            VolcanoSensor.BATTERY_VOLTAGE,
            VolcanoSensor.BATTERY_HEALTH,
            VolcanoSensor.CHARGE_CYCLES,
            VolcanoSensor.DISCHARGE_CYCLES,
            VolcanoSensor.CONNECTED,
            VolcanoSensor.RECONNECT,
            VolcanoSensor.DELAYED_RECONNECT,
            VolcanoSensor.FIND_DEVICE,
        }
    )

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the Crafty fields."""
        super().__init__(device)
        self.battery: int | None = None
        self.boost_temp: int | None = None
        self.boost_mode: bool | None = None
        self.superboost_mode: bool | None = None
        self.led_brightness: int | None = None
        self.auto_off_seconds: int | None = None
        self.auto_off_countdown: int | None = None
        self.heat_hours: int | None = None
        self.heat_minutes: int | None = None
        self.vibration: bool | None = None
        self.charge_led: bool | None = None
        self.permanent_bluetooth: bool | None = None
        self.find_mode: bool | None = None
        # Raw words, kept for diagnostics like the Volcano's registers.
        self.prj1: int | None = None
        self.prj2: int | None = None
        self.system_status: int | None = None
        self.battery_status1: int | None = None
        self.battery_status2: int | None = None
        self.charger_status: int | None = None
        # Spec §4.4: mV, mA (unsigned, so charging and heating both read
        # positive), mAh and counts. None where the device does not serve one.
        self.battery_voltage: int | None = None
        self.battery_current: int | None = None
        self.battery_full_capacity: int | None = None
        self.battery_design_capacity: int | None = None
        self.charge_cycles: int | None = None
        self.discharge_cycles: int | None = None
        self.error: bool | None = None
        self.needs_factory_reset: bool | None = None

    @property
    def firmware_generation(self) -> tuple[int, int] | None:
        """Major/minor of the reported firmware, if it has been read."""
        return parse_crafty_firmware(self.firmware_version)

    @property
    def is_plus(self) -> bool | None:
        """Whether this is a Crafty+ (firmware major >= 3), None until known."""
        generation = self.firmware_generation
        return None if generation is None else generation[0] >= CRAFTY_PLUS_MAJOR

    @property
    def is_old_firmware(self) -> bool | None:
        """Whether the settings characteristics are missing (< V02.51)."""
        generation = self.firmware_generation
        return None if generation is None else generation < CRAFTY_SETTINGS_FIRMWARE

    @property
    def model_name(self) -> str:
        """Crafty until the firmware says it is a Crafty+."""
        return "Crafty+" if self.is_plus else "Crafty"

    @property
    def charging(self) -> bool | None:
        """Whether the battery is charging; None if the device has not said."""
        if self.charger_status is None:
            return None
        return self.charger_status == CHARGER_STATUS_CHARGING

    @property
    def battery_health(self) -> int | None:
        """Full-charge capacity as a percentage of the design capacity."""
        full, design = self.battery_full_capacity, self.battery_design_capacity
        if full is None or not design:
            return None
        return round(full * 100 / design)

    @property
    def heat_time(self) -> int | None:
        """Lifetime heating time in minutes."""
        if self.heat_hours is None:
            return None
        return self.heat_hours * 60 + (self.heat_minutes or 0)

    def apply_prj1(self, word: int) -> None:
        """Decode PRJSTAT1 (spec §4.1)."""
        self.prj1 = word
        self.heater = bool(word & MASK_PRJSTAT_CRAFTY_ACTIVE)
        self.boost_mode = bool(word & MASK_PRJSTAT_BOOST_MODE_ENABLED)
        self.superboost_mode = bool(word & MASK_PRJSTAT_SUPERBOOST_MODE_ENABLED)
        self.needs_factory_reset = bool(word & MASK_PRJSTAT_NEEDS_FACTORY_RESET)
        self.apply_status_words()

    def apply_prj2(self, word: int) -> None:
        """Decode PRJSTAT2 (spec §4.2)."""
        self.prj2 = word
        self.vibration = not word & MASK_PRJSTAT2_DISABLE_VIBRATION
        self.charge_led = not word & MASK_PRJSTAT2_DISABLE_CHARGELED
        self.at_temperature = bool(word & MASK_PRJSTAT2_SET_TEMP_REACHED)
        self.find_mode = bool(word & MASK_PRJSTAT2_FIND_DEVICE)
        self.permanent_bluetooth = bool(word & MASK_PRJSTAT2_PERMANENT_BLUETOOTH)

    def apply_status_words(self) -> None:
        """Combine the app's 'contact support' masks (spec §4.3)."""
        self.error = bool(
            (self.prj1 or 0) & MASK_PRJSTAT_ERROR
            or (self.system_status or 0) & MASK_SYSTEM_ERROR
            or (self.battery_status1 or 0) & MASK_BATTERY1_ERROR
        )
