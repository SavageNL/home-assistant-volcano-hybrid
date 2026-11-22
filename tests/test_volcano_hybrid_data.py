"""Tests for the Volcano Hybrid data object."""

from __future__ import annotations

from . import FakeVolcanoBLE


def test_pending_write_state() -> None:
    """Pending writes drive the *_state values until confirmed."""
    data = FakeVolcanoBLE().data
    assert data.fan_state is None
    assert not data.is_assumed

    data.fan_write = True
    assert data.fan_state is True
    assert data.fan is None
    assert data.is_assumed

    # The device confirms the write: the pending write is cleared
    data.fan = True
    assert data.fan_write is None
    assert data.fan_state is True
    assert not data.fan_needs_write
    assert not data.is_assumed


def test_pending_write_needs_retry() -> None:
    """A pending write stays pending while the device reports another state."""
    data = FakeVolcanoBLE().data
    data.heater = False
    data.heater_write = True
    assert data.heater_needs_write
    assert data.heater_state is True
    assert data.is_assumed

    data.set_temp = 180
    data.set_temp_write = 190
    assert data.set_temp_needs_write
    assert data.set_temp_state == 190

    data.clear_open_writes()
    assert not data.heater_needs_write
    assert not data.set_temp_needs_write
    assert data.heater_state is False
    assert data.set_temp_state == 180
    assert not data.is_assumed


def test_pending_write_dropped_when_already_confirmed() -> None:
    """
    A write matching the confirmed state never becomes pending.

    A pending write that matches the device state would otherwise linger and
    be replayed later, e.g. turning the device off right after the user turns
    it on with the device button.
    """
    data = FakeVolcanoBLE().data
    data.heater = False
    data.heater_write = False
    assert data.heater_write is None
    assert not data.heater_needs_write
    assert not data.is_assumed

    data.fan = True
    data.fan_write = True
    assert data.fan_write is None
    assert not data.fan_needs_write

    data.set_temp = 190
    data.set_temp_write = 190
    assert data.set_temp_write is None
    assert not data.set_temp_needs_write


def test_is_on() -> None:
    """The device is on when the fan or the heater runs."""
    data = FakeVolcanoBLE().data
    assert data.is_on is False

    data.fan = True
    assert data.is_on is True

    data.fan = False
    data.heater = True
    assert data.is_on is True


def test_heat_time() -> None:
    """The heat time combines the hour and minute characteristics."""
    data = FakeVolcanoBLE().data
    assert data.heat_time is None

    data.heat_hours_changed = 2
    assert data.heat_time is None

    data.heat_minutes_changed = 30
    assert data.heat_time == 150


def test_heat_time_minutes_wrap_first() -> None:
    """The order seen on hardware: the minutes wrap before the hour ticks."""
    data = FakeVolcanoBLE().data
    data.heat_hours_changed, data.heat_minutes_changed = 1458, 59
    assert data.heat_time == 1458 * 60 + 59

    data.heat_minutes_changed = 0
    assert data.heat_time == 1459 * 60  # not 1458 * 60
    data.heat_hours_changed = 1459
    assert data.heat_time == 1459 * 60
    data.heat_minutes_changed = 1
    assert data.heat_time == 1459 * 60 + 1


def test_heat_time_hour_ticks_first() -> None:
    """The other order: the hour ticks before the minutes wrap."""
    data = FakeVolcanoBLE().data
    data.heat_hours_changed, data.heat_minutes_changed = 1458, 59

    data.heat_hours_changed = 1459
    assert data.heat_time == 1459 * 60  # not 1459:59, which would then drop
    data.heat_minutes_changed = 0
    assert data.heat_time == 1459 * 60
    data.heat_minutes_changed = 1
    assert data.heat_time == 1459 * 60 + 1


def test_heat_time_after_a_reconnect_hours_later() -> None:
    """A reading after hours of use elsewhere is taken as it is, in either order."""
    hours_first = FakeVolcanoBLE().data
    hours_first.heat_hours_changed, hours_first.heat_minutes_changed = 10, 50
    hours_first.heat_hours_changed = 12
    hours_first.heat_minutes_changed = 5
    assert hours_first.heat_time == 12 * 60 + 5  # not 13:05
    hours_first.heat_minutes_changed = 6
    assert hours_first.heat_time == 12 * 60 + 6

    minutes_first = FakeVolcanoBLE().data
    minutes_first.heat_hours_changed, minutes_first.heat_minutes_changed = 10, 50
    minutes_first.heat_minutes_changed = 5
    assert minutes_first.heat_time == 11 * 60 + 5  # provisional, never lower
    minutes_first.heat_hours_changed = 12
    assert minutes_first.heat_time == 12 * 60 + 5


def test_heat_time_never_drops_across_a_rollover() -> None:
    """Every published value is at least the previous one, in either order."""
    for order in ("minutes_first", "hours_first"):
        data = FakeVolcanoBLE().data
        data.heat_hours_changed, data.heat_minutes_changed = 10, 0
        seen = [data.heat_time]
        for hour in range(10, 13):
            for minute in range(1, 60):
                data.heat_minutes_changed = minute
                seen.append(data.heat_time)
            steps = (
                [("m", 0), ("h", hour + 1)]
                if order == "minutes_first"
                else [("h", hour + 1), ("m", 0)]
            )
            for which, value in steps:
                if which == "m":
                    data.heat_minutes_changed = value
                else:
                    data.heat_hours_changed = value
                seen.append(data.heat_time)
        assert seen == sorted(seen), order
        assert seen[-1] == 13 * 60


def test_on_and_off_time() -> None:
    """The on time is derived from the shut off and auto off time."""
    data = FakeVolcanoBLE().data
    assert data.current_auto_off_time is None
    assert data.current_on_time is None

    data.current_auto_off_time = 20.0
    assert data.current_auto_off_time == 20.0
    # Without a known shut off time the on time cannot be calculated
    assert data.current_on_time is None

    data.shut_off = 30
    assert data.current_on_time == 10.0

    # The device reports 0 when it is off
    data.current_auto_off_time = 0
    assert data.current_auto_off_time is None
    assert data.current_on_time is None


def test_current_temp_validation() -> None:
    """Out of range temperature readings are discarded."""
    data = FakeVolcanoBLE().data
    assert data.current_temp is None

    data.current_temp = 185
    assert data.current_temp == 185

    data.current_temp = 2310
    assert data.current_temp is None

    data.current_temp = 0
    assert data.current_temp is None


def test_provider_passthrough() -> None:
    """Connection details are read from the status provider."""
    fake = FakeVolcanoBLE()
    data = fake.data
    assert data.connected is False
    assert data.connected_addr is None

    fake.connected = True
    fake.device_rssi = -42
    assert data.connected is True
    assert data.connected_addr == "hci0"
    assert data.rssi == -42

    assert data.get("rssi") == -42
    assert data.get("connected") is True


def test_current_on_time_is_unknown_when_it_would_be_negative() -> None:
    """
    Lowering the auto-off setting mid-session leaves the on time underivable.

    The countdown is only loaded when an actuator switches on (spec §2), so a
    setting lowered below it would yield a negative on time.
    """
    data = FakeVolcanoBLE().data
    data.shut_off = 30
    data.current_auto_off_time = 50.0
    assert data.current_on_time is None

    data.shut_off = 60
    assert data.current_on_time == 10.0
