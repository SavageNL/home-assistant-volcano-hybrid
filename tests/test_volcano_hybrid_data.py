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
