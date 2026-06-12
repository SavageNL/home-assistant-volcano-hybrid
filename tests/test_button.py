"""Tests for the Volcano Hybrid buttons."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.components.button import (
    DOMAIN as BUTTON_DOMAIN,
)
from homeassistant.components.button import (
    SERVICE_PRESS,
)
from homeassistant.const import ATTR_ENTITY_ID

from . import FakeVolcanoBLE, get_entity_id, make_ble_device, make_service_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_reconnect_button(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Pressing the reconnect button disconnects and updates the device."""
    entity_id = get_entity_id(hass, "button", "reconnect")
    mock_volcano.device_rssi = None

    with (
        patch(
            "homeassistant.components.bluetooth.async_ble_device_from_address",
            return_value=make_ble_device(),
        ),
        patch(
            "homeassistant.components.bluetooth.async_last_service_info",
            return_value=make_service_info(),
        ),
    ):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    assert mock_volcano.disconnect_count == 1
    assert mock_volcano.manual_update_count == 1
    # The rssi of the last advertisement was passed to the device
    assert mock_volcano.device_rssi == -60
