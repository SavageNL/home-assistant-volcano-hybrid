"""Tests for the Volcano Hybrid binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.helpers import entity_registry as er

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_binary_sensors(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The binary sensors reflect the device data."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.auto_shutdown = True
    data.prv1_error = False
    data.prv2_error = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    auto_shutdown = hass.states.get(
        get_entity_id(hass, "binary_sensor", "auto_shutdown")
    )
    assert auto_shutdown is not None
    assert auto_shutdown.state == STATE_ON

    prv1 = hass.states.get(get_entity_id(hass, "binary_sensor", "prv1_error"))
    assert prv1 is not None
    assert prv1.state == STATE_OFF

    prv2 = hass.states.get(get_entity_id(hass, "binary_sensor", "prv2_error"))
    assert prv2 is not None
    assert prv2.state == STATE_ON

    connected = hass.states.get(get_entity_id(hass, "binary_sensor", "connected"))
    assert connected is not None
    assert connected.state == STATE_ON


async def test_status_binary_sensors(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The decoded status bits are exposed as binary sensors."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.at_temperature = True
    data.heater = True
    data.fan = False
    data.actuator_fault = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    ready = hass.states.get(get_entity_id(hass, "binary_sensor", "at_temperature"))
    assert ready is not None
    assert ready.state == STATE_ON

    heater = hass.states.get(get_entity_id(hass, "binary_sensor", "heater"))
    assert heater is not None
    assert heater.state == STATE_ON

    pump = hass.states.get(get_entity_id(hass, "binary_sensor", "fan"))
    assert pump is not None
    assert pump.state == STATE_OFF

    fault = hass.states.get(get_entity_id(hass, "binary_sensor", "actuator_fault"))
    assert fault is not None
    assert fault.state == STATE_OFF

    data.at_temperature = False
    data.actuator_fault = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    ready = hass.states.get(get_entity_id(hass, "binary_sensor", "at_temperature"))
    assert ready is not None
    assert ready.state == STATE_OFF

    fault = hass.states.get(get_entity_id(hass, "binary_sensor", "actuator_fault"))
    assert fault is not None
    assert fault.state == STATE_ON


async def test_service_mode_binary_sensor(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The burn-in mode held in the status registers is exposed."""
    entity_id = get_entity_id(hass, "binary_sensor", "service_mode")
    mock_volcano.connected = True
    data = mock_volcano.data
    data.service_mode = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    service_mode = hass.states.get(entity_id)
    assert service_mode is not None
    assert service_mode.state == STATE_OFF
    # Service mode drives the device to 230 °C on its own, so it is reported as
    # a problem rather than as a mode.
    assert service_mode.attributes["device_class"] == BinarySensorDeviceClass.PROBLEM

    data.service_mode = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    service_mode = hass.states.get(entity_id)
    assert service_mode is not None
    assert service_mode.state == STATE_ON


async def test_ready_sensor_is_enabled_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Ready is a user-facing entity; the other status bits are diagnostics."""
    registry = er.async_get(hass)

    ready = registry.async_get(get_entity_id(hass, "binary_sensor", "at_temperature"))
    assert ready is not None
    assert ready.disabled_by is None
    assert ready.entity_category is None

    for key in (
        "heater",
        "fan",
        "actuator_fault",
        "service_mode",
    ):
        entry = registry.async_get(get_entity_id(hass, "binary_sensor", key))
        assert entry is not None, key
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
        assert entry.entity_category is EntityCategory.DIAGNOSTIC, key


async def test_connected_sensor_follows_connection(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The connected sensor stays available and reports disconnects."""
    entity_id = get_entity_id(hass, "binary_sensor", "connected")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF

    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_ON

    mock_volcano.connected = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF
