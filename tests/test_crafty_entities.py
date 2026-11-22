"""Entity behaviour specific to the Crafty family."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.volcano_hybrid.volcano_ble import (
    DeviceFamily,
    UnsupportedCommandError,
)

from . import FakeDevice, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.parametrize(
    "device_family", [DeviceFamily.CRAFTY], indirect=True, ids=str
)


async def test_climate_has_no_fan_and_portable_limits(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """A Crafty climate stops at 210 °C and offers no fan mode."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.current_temp = 150
    data.set_temp = 185
    data.heater = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "climate", "volcano"))
    assert state is not None
    assert state.attributes["max_temp"] == 210
    assert state.attributes["min_temp"] == 40
    assert "fan_modes" not in state.attributes
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: state.entity_id, ATTR_TEMPERATURE: 190},
        blocking=True,
    )
    assert ("target_temperature", 190) in mock_volcano.commands


async def test_sensors_and_binary_sensors(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    """Battery, countdown and the status words are reported as the data holds them."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.battery = 85
    data.auto_off_countdown = 90
    data.heat_hours, data.heat_minutes = 1, 30
    data.prj1 = 0x0030
    data.system_status = 0x0200
    data.apply_status_words()
    data.boost_mode = True
    data.superboost_mode = False
    data.battery_current = 757
    data.battery_voltage = 4184
    data.battery_full_capacity = 2970
    data.battery_design_capacity = 3300
    data.charge_cycles = 565
    data.discharge_cycles = 195
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    assert hass.states.get(get_entity_id(hass, "sensor", "battery")).state == "85"
    for key, expected in (
        ("battery_current", "757"),
        ("battery_voltage", "4.184"),  # mV shown in V
        ("battery_health", "90"),
        ("charge_cycles", "565"),
        ("discharge_cycles", "195"),
    ):
        assert hass.states.get(get_entity_id(hass, "sensor", key)).state == expected
    assert (
        hass.states.get(get_entity_id(hass, "sensor", "auto_off_countdown")).state
        == "90"
    )
    assert (
        hass.states.get(get_entity_id(hass, "sensor", "system_status")).state
        == "0x0200"
    )
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "error")).state == (
        STATE_ON
    )
    assert hass.states.get(
        get_entity_id(hass, "binary_sensor", "boost_mode")
    ).state == (STATE_ON)
    assert hass.states.get(
        get_entity_id(hass, "binary_sensor", "superboost_mode")
    ).state == (STATE_OFF)


@pytest.mark.parametrize(
    ("key", "value", "command"),
    [
        ("boost_temp", 20, ("boost_temp", 20)),
        ("auto_off_seconds", 200, ("auto_off_seconds", 200)),
        ("led_brightness", 50, ("led_brightness", 50)),
    ],
)
async def test_numbers(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
    value: int,
    command: tuple[str, int],
) -> None:
    """Each number writes through to the device."""
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    entity_id = get_entity_id(hass, "number", key)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )
    assert command in mock_volcano.commands


@pytest.mark.parametrize("key", ["charge_led", "permanent_bluetooth", "vibration"])
async def test_switches(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
) -> None:
    """Each switch reflects the data and writes through."""
    mock_volcano.connected = True
    setattr(mock_volcano.data, key, True)
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    entity_id = get_entity_id(hass, "switch", key)
    assert hass.states.get(entity_id).state == STATE_ON
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert (key, False) in mock_volcano.commands


async def test_find_device_button_and_unsupported_error(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    """The button calls find-my-device; a refusal becomes a translated error."""
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    entity_id = get_entity_id(hass, "button", "find_device")
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert ("find_device", None) in mock_volcano.commands

    mock_volcano.error = UnsupportedCommandError("not a Crafty+")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
    assert err.value.translation_key == "not_supported"
