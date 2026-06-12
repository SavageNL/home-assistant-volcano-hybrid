"""Tests for the Volcano Hybrid diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.diagnostics import REDACTED

from custom_components.volcano_hybrid.diagnostics import (
    async_get_config_entry_diagnostics,
)

from . import FakeVolcanoBLE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_diagnostics(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The diagnostics contain the device state with identifiers redacted."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.serial_number = "VH123456"
    data.firmware_version = "V01.23"
    data.current_temp = 185
    data.set_temp = 190
    data.heater = True
    data.fan = False
    data.shut_off = 30

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["entry_data"]["address"] == REDACTED
    assert diagnostics["device"]["serial_number"] == REDACTED
    assert diagnostics["connection"]["connected_addr"] == REDACTED

    assert diagnostics["device"]["firmware_version"] == "V01.23"
    assert diagnostics["connection"]["connected"] is True
    assert diagnostics["connection"]["rssi"] == -60
    assert diagnostics["state"]["current_temp"] == 185
    assert diagnostics["state"]["set_temp"] == 190
    assert diagnostics["state"]["heater"] is True
    assert diagnostics["state"]["fan"] is False
    assert diagnostics["state"]["shut_off"] == 30
    assert diagnostics["state"]["is_assumed"] is False
