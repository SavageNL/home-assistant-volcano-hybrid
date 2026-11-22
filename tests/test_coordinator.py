"""Tests for the Volcano Hybrid coordinator connect scheduling."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from bleak import BleakError
from habluetooth import get_manager
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.volcano_hybrid.coordinator import whole_degree_target
from custom_components.volcano_hybrid.volcano_ble import (
    CommandNotConfirmedError,
    UnsupportedCommandError,
)

from . import FakeVolcanoBLE, get_entity_id, make_ble_device, make_service_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

_DEVICE_PATCH = "homeassistant.components.bluetooth.async_ble_device_from_address"
_INFO_PATCH = "homeassistant.components.bluetooth.async_last_service_info"


async def test_enable_debounces_scheduled_connect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Scheduling a connect while one is pending does not stack attempts."""
    coordinator = init_integration.runtime_data

    with (
        patch(_DEVICE_PATCH, return_value=make_ble_device()),
        patch(_INFO_PATCH, return_value=make_service_info()),
    ):
        # The second call is a no-op while the first attempt is still pending.
        await coordinator.async_set_auto_connect(enabled=True)
        await coordinator.async_set_auto_connect(enabled=True)
        assert mock_volcano.manual_update_count == 0

        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=coordinator.auto_connect_delay + 1),
        )
        await hass.async_block_till_done()

        assert mock_volcano.manual_update_count >= 1


async def test_poll_refreshes_connected_device_that_stopped_advertising(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    The periodic poll refreshes a connected device that no longer advertises.

    Regression test: the vaporizer stops advertising once something is
    connected to it, so it drops out of the Bluetooth address cache and
    ``async_ble_device_from_address`` starts returning None. Gating the refresh
    on that silently skipped every poll for as long as the connection lasted,
    which stopped the current temperature from ever being re-read and left it
    frozen on the last notification that arrived.
    """
    coordinator = init_integration.runtime_data
    mock_volcano.connected = True
    mock_volcano.manual_update_count = 0

    with patch(_DEVICE_PATCH, return_value=None), patch(_INFO_PATCH, return_value=None):
        async_fire_time_changed(
            hass,
            dt_util.utcnow() + coordinator.update_interval + timedelta(seconds=1),
        )
        await hass.async_block_till_done()

    assert mock_volcano.manual_update_count >= 1


async def test_poll_does_not_connect_without_a_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A disconnected device is not refreshed until it has been seen again."""
    coordinator = init_integration.runtime_data
    mock_volcano.connected = False
    mock_volcano.manual_update_count = 0

    with patch(_DEVICE_PATCH, return_value=None), patch(_INFO_PATCH, return_value=None):
        async_fire_time_changed(
            hass,
            dt_util.utcnow() + coordinator.update_interval + timedelta(seconds=1),
        )
        await hass.async_block_till_done()

    assert mock_volcano.manual_update_count == 0


async def test_scheduled_connect_skipped_when_already_connected(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A scheduled connect does nothing if the device connected meanwhile."""
    coordinator = init_integration.runtime_data

    with (
        patch(_DEVICE_PATCH, return_value=make_ble_device()),
        patch(_INFO_PATCH, return_value=make_service_info()),
    ):
        await coordinator.async_set_auto_connect(enabled=True)
        # The device connects (e.g. physically) before the timer fires.
        mock_volcano.connected = True

        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=coordinator.auto_connect_delay + 1),
        )
        await hass.async_block_till_done()

        assert mock_volcano.manual_update_count == 0


async def test_unsupported_command_raises_translated_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A command the device cannot carry out raises a translated error."""
    mock_volcano.connected = True
    mock_volcano.error = UnsupportedCommandError()

    with pytest.raises(HomeAssistantError) as err:
        await init_integration.runtime_data.set_vibration(on=True)
    assert err.value.translation_key == "not_supported"


async def test_unconfirmed_command_raises_translated_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A write the device does not take on raises a translated error."""
    mock_volcano.connected = True
    mock_volcano.error = CommandNotConfirmedError()

    with pytest.raises(HomeAssistantError) as err:
        await init_integration.runtime_data.set_vibration(on=True)
    assert err.value.translation_key == "not_confirmed"


@pytest.mark.parametrize(
    ("target", "current", "expected"),
    [
        # A whole °C, as Home Assistant in °C sends it, is taken as is.
        (195.0, 190, 195),
        (190.0, 190, 190),
        # A °F step that rounds onto the current target moves one degree anyway:
        # 366 °F is 185.56 °C, from 186 °C (shown as 367 °F) that is a step down.
        (185.56, 186, 185),
        (185.56, 185, 186),
        # Float noise from converting a whole °C back and forth is no step.
        (229.99999, 230, 230),
        (190.000001, 190, 190),
        # Rounded to the nearest degree otherwise, and without a known target.
        (190.4, 185, 190),
        (190.6, 185, 191),
        (185.56, None, 186),
    ],
)
def test_whole_degree_target(target: float, current: int | None, expected: int) -> None:
    """A requested target becomes the whole °C the device stores."""
    assert whole_degree_target(target, current) == expected


async def test_set_target_temperature_is_rounded_and_clamped(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The coordinator sends a whole °C within the device's range."""
    mock_volcano.connected = True
    mock_volcano.data.set_temp = 186
    coordinator = init_integration.runtime_data

    await coordinator.set_target_temperature(185.56)
    assert mock_volcano.commands[-1] == ("target_temperature", 185)

    mock_volcano.data.set_temp = 230
    await coordinator.set_target_temperature(230.6)
    assert mock_volcano.commands[-1] == ("target_temperature", 230)


async def test_refresh_after_unload_does_not_reconnect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    Once the entry is unloaded, a refresh no longer reaches the device.

    The coordinator's shutdown has to run the base class's as well: that is
    what marks the coordinator shut down, and without it a refresh after unload
    would still connect, since auto-connect is left enabled.
    """
    coordinator = init_integration.runtime_data
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    updates = mock_volcano.manual_update_count

    with (
        patch(_DEVICE_PATCH, return_value=make_ble_device()),
        patch(_INFO_PATCH, return_value=make_service_info()),
    ):
        await coordinator.async_refresh()

    assert mock_volcano.manual_update_count == updates


async def test_unload_cancels_a_connect_in_flight(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    A connect that is still running when the entry unloads is cancelled.

    Left running, it could finish after the shutdown's disconnect and leave a
    connection behind that nothing owns any more.
    """
    coordinator = init_integration.runtime_data
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = False

    async def blocking_update(_device: object = None) -> object:
        nonlocal cancelled
        mock_volcano.manual_update_count += 1
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        mock_volcano.connected = True
        return mock_volcano.data

    mock_volcano.async_manual_update = blocking_update  # type: ignore[method-assign]

    try:
        with (
            patch(_DEVICE_PATCH, return_value=make_ble_device()),
            patch(_INFO_PATCH, return_value=make_service_info()),
        ):
            # The device advertises; the connect runs once the delay is up.
            get_manager().scanner_adv_received(make_service_info())
            async_fire_time_changed(
                hass,
                dt_util.utcnow()
                + timedelta(seconds=coordinator.auto_connect_delay + 1),
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            disconnects = mock_volcano.disconnect_count

            # Not followed by async_block_till_done: a connect that unload
            # failed to cancel would block it for good.
            await hass.config_entries.async_unload(init_integration.entry_id)
            for _ in range(5):
                await asyncio.sleep(0)
            assert cancelled
    finally:
        # Never leave the connect blocked, so a failure cannot hang the test.
        release.set()
        await hass.async_block_till_done()

    assert mock_volcano.disconnect_count > disconnects
    assert not mock_volcano.connected


async def test_failed_read_is_update_failed_and_keeps_the_device_available(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A Bluetooth read error is one log line, not an unexpected-error traceback."""
    coordinator = init_integration.runtime_data
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    async def failing_update(device: object = None) -> object:
        msg = "Bluetooth GATT Error address=AA handle=71 error=133 description=Error"
        raise BleakError(msg)

    mock_volcano.async_manual_update = failing_update  # type: ignore[method-assign,assignment]
    with patch(_DEVICE_PATCH, return_value=None), patch(_INFO_PATCH, return_value=None):
        async_fire_time_changed(
            hass,
            dt_util.utcnow() + coordinator.update_interval + timedelta(seconds=1),
        )
        await hass.async_block_till_done()

    assert "Unexpected error" not in caplog.text
    assert "Reading from the device failed" in caplog.text
    assert "error=133" in caplog.text
    # Still connected, so still available.
    assert coordinator.last_update_success
    climate = hass.states.get(get_entity_id(hass, "climate", "volcano"))
    assert climate is not None
    assert climate.state != "unavailable"
