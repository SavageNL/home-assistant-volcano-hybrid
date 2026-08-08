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
    data.at_temperature = True
    data.actuator_fault = False

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
    assert diagnostics["state"]["at_temperature"] is True
    assert diagnostics["state"]["actuator_fault"] is False


async def test_diagnostics_include_raw_registers_and_history(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The raw status registers and error history are reported for support."""
    data = mock_volcano.data
    data.prj1 = 0x2020
    data.prj2 = 0x0000
    data.prj3 = 0x0400
    data.hist1 = "0011223344556677"
    data.hist2 = "8899aabbccddeeff"

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    registers = diagnostics["registers"]
    assert registers["prj1"] == "0x2020"
    assert registers["prj2"] == "0x0000"
    assert registers["prj3"] == "0x0400"
    assert registers["hist1"] == "0011223344556677"
    assert registers["hist2"] == "8899aabbccddeeff"


async def test_diagnostics_registers_before_connect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Registers that were never read are reported as null, not formatted."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["registers"] == {
        "prj1": None,
        "prj2": None,
        "prj3": None,
        "hist1": None,
        "hist2": None,
    }
