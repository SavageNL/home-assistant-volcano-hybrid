"""Tests for the Volcano Hybrid numbers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.number import (
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize(
    ("key", "current", "target"),
    [
        ("shut_off", 30, 45),
        ("led_brightness", 70, 100),
    ],
)
async def test_number(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    key: str,
    current: int,
    target: int,
) -> None:
    """The number reflects the device data and sends commands."""
    entity_id = get_entity_id(hass, "number", key)

    mock_volcano.connected = True
    setattr(mock_volcano.data, key, current)
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == current

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: target},
        blocking=True,
    )
    assert (key, target) in mock_volcano.commands
