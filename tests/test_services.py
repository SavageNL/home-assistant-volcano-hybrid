"""Tests for the wait_for_temperature action."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.volcano_hybrid.const import DOMAIN
from custom_components.volcano_hybrid.services import SERVICE_WAIT_FOR_TEMPERATURE

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _heating(hass: HomeAssistant, fake: FakeVolcanoBLE, current: int) -> str:
    """Put the fake in a connected, heating state and return the climate entity."""
    fake.connected = True
    fake.data.set_temp = 190
    fake.data.heater = True
    fake.data.current_temp = current
    fake.data_updated()
    await hass.async_block_till_done()
    return get_entity_id(hass, "climate", "volcano")


async def _settle() -> None:
    """Let a started wait run up to the point where it listens for updates."""
    for _ in range(20):
        await asyncio.sleep(0)


async def _wait(
    hass: HomeAssistant, entity_id: str, **data: Any
) -> dict[str, Any] | None:
    """Call the action asking for its response, and return this entity's part."""
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_WAIT_FOR_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, **data},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    result = response[entity_id]
    assert isinstance(result, dict)
    return result


async def test_reached_already(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device already at its target, less the tolerance, is reached at once."""
    entity_id = await _heating(hass, mock_volcano, current=189)

    assert await _wait(hass, entity_id) == {"reached": True, "reason": None}
    # Without a response, success is just a call that returns.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_WAIT_FOR_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )


async def test_waits_for_the_temperature(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The action returns once a reading reaches the target."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    task = asyncio.ensure_future(_wait(hass, entity_id, tolerance=0))
    for current in (170, 189):
        mock_volcano.data.current_temp = current
        mock_volcano.data_updated()
        await _settle()
        assert not task.done()

    mock_volcano.data.current_temp = 190
    mock_volcano.data_updated()
    assert await task == {"reached": True, "reason": None}


def _disconnect(fake: FakeVolcanoBLE) -> None:
    fake.connected = False


def _heater_off(fake: FakeVolcanoBLE) -> None:
    fake.data.heater = False


def _new_target(fake: FakeVolcanoBLE) -> None:
    fake.data.set_temp = 200


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (_disconnect, "disconnected"),
        (_heater_off, "heater_off"),
        (_new_target, "target_changed"),
    ],
)
async def test_ends_early_when_the_target_cannot_be_reached(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    change: Callable[[FakeVolcanoBLE], None],
    reason: str,
) -> None:
    """The wait ends straight away instead of sitting out its timeout."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    task = asyncio.ensure_future(_wait(hass, entity_id))
    await _settle()
    assert not task.done()

    change(mock_volcano)
    mock_volcano.data_updated()
    assert await task == {"reached": False, "reason": reason}


async def test_failure_raises_without_a_response(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A caller that does not ask for the response gets a translated error."""
    entity_id = await _heating(hass, mock_volcano, current=150)
    mock_volcano.data.heater = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WAIT_FOR_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
    assert err.value.translation_key == "wait_heater_off"


async def test_timeout(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device that does not heat up in time ends the wait."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    assert await _wait(hass, entity_id, timeout=0.01) == {
        "reached": False,
        "reason": "timeout",
    }


async def test_not_connected(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device that is not connected cannot be waited for."""
    entity_id = get_entity_id(hass, "climate", "volcano")

    # Home Assistant refuses the action on an unavailable entity before the
    # integration sees it.
    with pytest.raises(HomeAssistantError):
        await _wait(hass, entity_id)


async def test_tolerance_is_in_the_configured_unit(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """With Home Assistant in °F, the tolerance is taken in °F."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity_id = await _heating(hass, mock_volcano, current=189)

    # 1 °F is 0.56 °C, not enough for a reading 1 °C under the target.
    assert await _wait(hass, entity_id, tolerance=1, timeout=0.01) == {
        "reached": False,
        "reason": "timeout",
    }
    # 1.8 °F is the 1 °C it is short.
    assert await _wait(hass, entity_id, tolerance=1.8) == {
        "reached": True,
        "reason": None,
    }
