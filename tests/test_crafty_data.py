"""Tests for decoding what a Crafty reports (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble.const import (
    DeviceFamily,
    VolcanoSensor,
)
from custom_components.volcano_hybrid.volcano_ble.crafty_data import (
    MASK_PRJSTAT2_SET_TEMP_REACHED,
    MASK_PRJSTAT_BOOST_MODE_ENABLED,
    MASK_PRJSTAT_CRAFTY_ACTIVE,
    CraftyData,
    decode_target,
    parse_crafty_firmware,
)

from . import FakeDevice


def _data() -> CraftyData:
    return FakeDevice(DeviceFamily.CRAFTY).data


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1850, 185),  # °C x10
        (2100, 210),  # the top of the range is still Celsius
        (3650, 185),  # 365.0 °F: the device reports °F x10 when set to °F (§3.1)
    ],
)
def test_decode_target(raw: int, expected: int) -> None:
    """A target over 210 is Fahrenheit and is converted."""
    assert decode_target(raw) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [("V02.51", (2, 51)), ("V03.02", (3, 2)), ("V02.49", (2, 49)), ("junk", None)],
)
def test_parse_crafty_firmware(version: str, expected: tuple[int, int] | None) -> None:
    """Major is characters 1-2, minor the last two, as the vendor app reads it."""
    assert parse_crafty_firmware(version) == expected


def test_firmware_generation_decides_the_model() -> None:
    """Crafty+ is major >= 3; below V02.51 the settings side is missing (§6)."""
    data = _data()
    assert data.model_name == "Crafty"
    assert data.is_plus is None
    data.firmware_version = "V02.49"
    assert data.is_old_firmware is True
    assert data.is_plus is False
    data.firmware_version = "V03.02"
    assert data.is_old_firmware is False
    assert data.is_plus is True
    assert data.model_name == "Crafty+"


def test_prj1_drives_heater_and_boost_flags() -> None:
    """PRJSTAT1 bit 4 is the heater, bits 5/6 the boost modes (§4.1)."""
    data = _data()
    data.apply_prj1(MASK_PRJSTAT_CRAFTY_ACTIVE | MASK_PRJSTAT_BOOST_MODE_ENABLED)
    assert data.heater is True
    assert data.boost_mode is True
    assert data.superboost_mode is False
    assert data.error is False
    assert data.needs_factory_reset is False
    assert data.prj1 == 0x0030

    data.apply_prj1(0x8008)
    assert data.heater is False
    assert data.error is True
    assert data.needs_factory_reset is True


def test_prj2_polarity() -> None:
    """The vibration and charge-LED bits are 'disabled' bits (§4.2)."""
    data = _data()
    data.apply_prj2(0x0003 | MASK_PRJSTAT2_SET_TEMP_REACHED)
    assert data.vibration is False
    assert data.charge_led is False
    assert data.at_temperature is True
    assert data.find_mode is False
    assert data.permanent_bluetooth is False

    data.apply_prj2(0x1008)
    assert data.vibration is True
    assert data.charge_led is True
    assert data.find_mode is True
    assert data.permanent_bluetooth is True


def test_status_words_raise_error() -> None:
    """The battery/system words flag the same 'contact support' masks the app tests."""
    data = _data()
    data.prj1 = 0
    data.system_status = 0x0200
    data.apply_status_words()
    assert data.error is True
    data.system_status = 0
    data.battery_status1 = 0x0400
    data.apply_status_words()
    assert data.error is True
    data.battery_status1 = 0x0003  # "please charge": not an error
    data.apply_status_words()
    assert data.error is False


def test_heat_time_and_capabilities() -> None:
    """Lifetime minutes combine hours and minutes; the family owns its keys."""
    data = _data()
    assert data.heat_time is None
    data.heat_hours = 2
    data.heat_minutes = 30
    assert data.heat_time == 150
    assert VolcanoSensor.BATTERY in data.capabilities
    assert VolcanoSensor.PUMP_ACTIVE not in data.capabilities
    assert data.MAX_TEMP == 210


def test_current_temperature_above_the_target_range_is_kept() -> None:
    """
    A reading past the 210 °C target maximum is real (boost overshoots it).

    Only what no heater reaches counts as "no reading".
    """
    data = _data()
    data.current_temp = 220
    assert data.current_temp == 220
    data.current_temp = 231
    assert data.current_temp is None
    # The target range is unchanged.
    assert data.MAX_TEMP == 210


@pytest.mark.parametrize(
    ("status", "charging"),
    [(None, None), (0, False), (1, False), (2, True), (3, False)],
)
def test_charging_is_charger_status_two(
    status: int | None, charging: bool | None
) -> None:
    """Only 2 means charging (spec §4.4); other plugged-in states do not."""
    data = _data()
    data.charger_status = status
    assert data.charging is charging


@pytest.mark.parametrize(
    ("full", "design", "health"),
    [
        (None, 3300, None),
        (3300, None, None),
        (3300, 0, None),
        (3300, 3300, 100),
        (2970, 3300, 90),
        (3400, 3300, 103),
    ],
)
def test_battery_health_is_full_over_design(
    full: int | None, design: int | None, health: int | None
) -> None:
    """Full-charge over design capacity, unknown without both; not clamped."""
    data = _data()
    data.battery_full_capacity = full
    data.battery_design_capacity = design
    assert data.battery_health == health
