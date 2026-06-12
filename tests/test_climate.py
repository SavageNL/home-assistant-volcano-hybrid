"""Tests for the Volcano Hybrid climate entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from bleak import BleakError
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
)
from homeassistant.exceptions import HomeAssistantError

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_climate_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The climate entity reflects the device state."""
    entity_id = get_entity_id(hass, "climate", "volcano")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    mock_volcano.connected = True
    data = mock_volcano.data
    data.current_temp = 185
    data.set_temp = 190
    data.heater = True
    data.fan = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 185
    assert state.attributes[ATTR_TEMPERATURE] == 190
    assert state.attributes[ATTR_FAN_MODE] == "off"
    assert not state.attributes.get(ATTR_ASSUMED_STATE, False)

    data.fan = True
    data.heater = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_FAN_MODE] == "on"


async def test_climate_assumed_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The climate entity is marked assumed while writes are unconfirmed."""
    entity_id = get_entity_id(hass, "climate", "volcano")

    mock_volcano.connected = True
    data = mock_volcano.data
    data.heater = False
    data.heater_write = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_ASSUMED_STATE] is True


async def test_climate_services(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The climate services send the matching device commands."""
    entity_id = get_entity_id(hass, "climate", "volcano")

    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 195},
        blocking=True,
    )
    assert ("target_temperature", 195) in mock_volcano.commands

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    assert ("heater", True) in mock_volcano.commands

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    assert ("heater", False) in mock_volcano.commands

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_FAN_MODE: "on"},
        blocking=True,
    )
    assert ("fan", True) in mock_volcano.commands


async def test_climate_command_not_delivered(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A command that cannot be delivered raises a translated error."""
    entity_id = get_entity_id(hass, "climate", "volcano")
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    mock_volcano.write_result = False

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.HEAT},
            blocking=True,
        )
    assert err.value.translation_key == "not_connected"


async def test_climate_command_ble_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A BLE failure while sending a command raises a translated error."""
    entity_id = get_entity_id(hass, "climate", "volcano")
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    mock_volcano.error = BleakError("boom")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 195},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"
