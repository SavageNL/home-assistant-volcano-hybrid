"""Tests for the pending-write tracking shared by every device family."""

from __future__ import annotations

from custom_components.volcano_hybrid.volcano_ble.const import DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.data import DeviceData, TrackedValue

from . import FakeVolcanoBLE


def test_tracked_value_records_before_confirmation() -> None:
    """A pending write drives the state until the device confirms it."""
    tracked: TrackedValue[bool] = TrackedValue()
    assert tracked.state is None
    assert not tracked.needs_write

    tracked.pending = True
    assert tracked.state is True
    assert tracked.value is None
    assert tracked.needs_write

    tracked.value = True
    assert tracked.pending is None
    assert tracked.state is True
    assert not tracked.needs_write


def test_tracked_value_matching_the_device_never_goes_pending() -> None:
    """A write equal to the confirmed value is dropped, so it cannot be replayed."""
    tracked: TrackedValue[int] = TrackedValue()
    tracked.value = 180
    tracked.pending = 180
    assert tracked.pending is None
    assert not tracked.needs_write


def test_tracked_value_stays_pending_while_the_device_disagrees() -> None:
    """The device reporting another value keeps the write pending."""
    tracked: TrackedValue[int] = TrackedValue()
    tracked.value = 180
    tracked.pending = 190
    tracked.value = 185
    assert tracked.needs_write
    assert tracked.state == 190

    tracked.clear()
    assert tracked.pending is None
    assert tracked.state == 185


def test_base_data_defaults() -> None:
    """A bare data object claims nothing before the device has reported."""
    data = FakeVolcanoBLE().data
    assert isinstance(data, DeviceData)
    assert data.family is DeviceFamily.VOLCANO_HYBRID
    assert data.model_name == "Volcano Hybrid"
    assert data.is_heating is None
    assert not data.is_assumed
    assert "at_temperature" in data.capabilities


def test_tracked_value_discard_only_drops_its_own_write() -> None:
    """Forgetting an unsent write keeps a newer one recorded meanwhile."""
    tracked: TrackedValue[bool] = TrackedValue()
    tracked.value = False
    tracked.pending = True
    tracked.discard(True)
    assert tracked.pending is None

    # "On" failed, but "off" was issued while it was failing; "off" stays.
    tracked.value = True
    tracked.pending = False
    tracked.discard(True)
    assert tracked.pending is False
