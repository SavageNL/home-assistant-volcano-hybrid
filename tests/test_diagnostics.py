"""Tests for the Volcano Hybrid diagnostics."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.volcano_hybrid.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.volcano_hybrid.volcano_ble import DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.crafty_data import CraftyData

from . import FakeDevice, FakeVolcanoBLE

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
    data.model = "HYBRID"
    data.mains_voltage = "230VAC"
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
    # The device's own identity strings, not the fallbacks the registry shows.
    assert diagnostics["device"]["model"] == "HYBRID"
    assert diagnostics["device"]["mains_voltage"] == "230VAC"
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
    data.prj4 = 0x1234
    data.prj5 = 0x5678
    data.hist1 = "6161616161617261"
    data.hist2 = "0000000000000000"

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    registers = diagnostics["registers"]
    assert registers["prj1"] == "0x2020"
    assert registers["prj2"] == "0x0000"
    assert registers["prj3"] == "0x0400"
    assert registers["prj4"] == "0x1234"
    assert registers["prj5"] == "0x5678"
    assert registers["hist1"] == "6161616161617261"
    assert registers["hist2"] == "0000000000000000"


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
        "prj4": None,
        "prj5": None,
        "hist1": None,
        "hist2": None,
    }


@pytest.mark.parametrize("device_family", [DeviceFamily.VENTY], indirect=True, ids=str)
async def test_diagnostics_for_a_venty(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """Every field the family holds is dumped; the Volcano-only keys are absent."""
    mock_volcano.data.battery = 85
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diagnostics["entry_data"]["model"] == "venty"
    assert diagnostics["state"]["battery"] == 85
    assert diagnostics["state"]["heater_mode_name"] is None
    assert "registers" not in diagnostics
    assert "fan" not in diagnostics["state"]


@pytest.mark.parametrize("device_family", [DeviceFamily.CRAFTY], indirect=True, ids=str)
async def test_diagnostics_for_a_crafty(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """A Crafty dump carries its raw status words, rendered like the Volcano's."""
    data = mock_volcano.data
    assert isinstance(data, CraftyData)
    data.prj1 = 0x0010
    data.prj2 = 0x0400
    data.system_status = 0x0003
    data.battery_status1 = 0x1234
    data.battery_status2 = None
    data.battery = 60

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["registers"] == {
        "prj1": "0x0010",
        "prj2": "0x0400",
        "system_status": "0x0003",
        "battery_status1": "0x1234",
        "battery_status2": None,
    }
    assert diagnostics["state"]["battery"] == 60
    assert "extended" not in diagnostics
    # Reported once, under registers.
    for name in diagnostics["registers"]:
        assert name not in diagnostics["state"]
    # The download Home Assistant offers is this dict as JSON.
    json.dumps(diagnostics)


@pytest.mark.parametrize(
    "device_family",
    [DeviceFamily.VOLCANO_HYBRID, DeviceFamily.VENTY, DeviceFamily.VEAZY],
    indirect=True,
    ids=str,
)
async def test_diagnostics_are_json(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Every family's dump serialises as the JSON download it becomes."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    json.dumps(diagnostics)


@pytest.mark.parametrize("device_family", [DeviceFamily.CRAFTY], indirect=True, ids=str)
async def test_diagnostics_include_extended_values(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """The values only community clients read are added, raw, when there are any."""
    mock_volcano.extended_diagnostics = {"battery_voltage": 4012, "charge_cycles": None}

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["extended"] == {"battery_voltage": 4012, "charge_cycles": None}
    json.dumps(diagnostics)


async def test_diagnostics_include_the_gatt_table(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """The service table is reported with each characteristic's properties."""
    before = await async_get_config_entry_diagnostics(hass, init_integration)
    assert before["gatt"] == {}
    mock_volcano.gatt = {"svc": {"char": ["notify", "read"]}}

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["gatt"] == {"svc": {"char": ["notify", "read"]}}
    json.dumps(diagnostics)
