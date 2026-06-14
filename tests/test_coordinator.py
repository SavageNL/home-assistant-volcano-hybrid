"""Tests for the Volcano Hybrid coordinator connect scheduling."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from . import FakeVolcanoBLE, make_ble_device, make_service_info

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
