"""Tests for the Volcano Hybrid binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import STATE_OFF, STATE_ON

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
