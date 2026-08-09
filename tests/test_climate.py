"""Tests for the Volcano Hybrid climate entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from bleak import BleakError
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
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
    STATE_UNKNOWN,
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


async def test_climate_unknown_before_device_data(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    Nothing is claimed about the device before its state has been read.

    Regression test: the entity started out reporting 0 degrees current,
    40 degrees target and "off", which the recorder stored as if they were
    readings every time the entry was reloaded.
    """
    entity_id = get_entity_id(hass, "climate", "volcano")

    # Connected, but no characteristic has been read yet.
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert state.attributes[ATTR_FAN_MODE] is None


async def test_climate_hvac_action_tracks_the_temperature_gap(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    Heating is reported from the temperatures, not the device's "reached" bit.

    The device's setpoint-reached signal only clears once the setpoint moves
    more than 2 degrees above the current reading, so it keeps claiming to be
    at temperature through small adjustments. Nothing is reported while the
    heater holds temperature, which leaves the card showing the mode.
    """
    entity_id = get_entity_id(hass, "climate", "volcano")

    # Connected, but no status register read yet: nothing is claimed. Home
    # Assistant leaves the attribute out entirely while the action is unknown.
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert ATTR_HVAC_ACTION not in state.attributes

    data = mock_volcano.data
    data.heater = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF

    # Switched on, but the temperatures have not been read yet.
    data.heater = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert ATTR_HVAC_ACTION not in state.attributes

    # Heating up, still below the setpoint.
    data.current_temp = 100
    data.set_temp = 180
    data.at_temperature = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING

    # Holding at the setpoint: no action, so the card falls back to the mode.
    data.current_temp = 180
    data.at_temperature = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert ATTR_HVAC_ACTION not in state.attributes

    # Regression: a one degree raise. The device still reports having reached
    # the setpoint, but it is heating, and that is what has to be shown.
    data.set_temp = 181
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING

    # Setpoint dropped below the current reading: coasting down, not heating.
    data.set_temp = 160
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert ATTR_HVAC_ACTION not in state.attributes


async def test_climate_hvac_action_idles_while_cooling(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """
    A switched-off but still hot device idles while its display stays lit.

    The device gives no signal for this: its status register reads all zeroes
    the instant the heater goes off, however hot the block still is. It is
    inferred from the temperature the device keeps reporting and the setting
    that decides whether the display stays on for it.
    """
    entity_id = get_entity_id(hass, "climate", "volcano")

    mock_volcano.connected = True
    data = mock_volcano.data
    data.heater = False
    data.current_temp = 170
    data.display_on_cooling = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    # Cooled past the point where the device blanks its display.
    data.current_temp = 39
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF

    # With the display set to stay off, there is nothing to idle for.
    data.current_temp = 170
    data.display_on_cooling = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


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
