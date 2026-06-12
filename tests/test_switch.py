"""Tests for the Volcano Hybrid switches."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize("key", ["showing_celsius", "display_on_cooling", "vibration"])
async def test_switch(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    key: str,
) -> None:
    """The switch reflects the device data and sends commands."""
    entity_id = get_entity_id(hass, "switch", key)

    mock_volcano.connected = True
    setattr(mock_volcano.data, key, True)
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_ON

    setattr(mock_volcano.data, key, False)
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    assert (key, True) in mock_volcano.commands

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    assert (key, False) in mock_volcano.commands
