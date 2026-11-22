"""Tests for the wait_for_temperature action."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.volcano_hybrid.const import DOMAIN
from custom_components.volcano_hybrid.coordinator import (
    WAIT_DISCONNECTED,
    WAIT_GRACE,
    WAIT_HEATER_OFF,
)
from custom_components.volcano_hybrid.services import SERVICE_WAIT_FOR_TEMPERATURE

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


# A grace period long enough to see a blip come and go, short enough to wait out.
GRACE = 0.2


@pytest.fixture
def short_grace() -> Generator[None]:
    """Shorten the grace periods so a test can outlast them."""
    with patch.dict(WAIT_GRACE, {WAIT_HEATER_OFF: GRACE, WAIT_DISCONNECTED: GRACE}):
        yield


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
    """A device already at its target is reached at once."""
    entity_id = await _heating(hass, mock_volcano, current=190)

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
    short_grace: None,
    change: Callable[[FakeVolcanoBLE], None],
    reason: str,
) -> None:
    """The wait ends after the grace period instead of sitting out its timeout."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    task = asyncio.ensure_future(_wait(hass, entity_id))
    await _settle()
    assert not task.done()

    change(mock_volcano)
    mock_volcano.data_updated()
    # Ended by the grace period running out, with no further update.
    async with asyncio.timeout(5):
        assert await task == {"reached": False, "reason": reason}


@pytest.mark.parametrize("change", [_disconnect, _heater_off])
async def test_a_blip_does_not_end_the_wait(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    short_grace: None,
    change: Callable[[FakeVolcanoBLE], None],
) -> None:
    """
    A heater or connection that comes straight back keeps the wait going.

    A Volcano switching on often reports its heater off for a second or two,
    and a connection can drop for a few seconds while the device heats on.
    """
    entity_id = await _heating(hass, mock_volcano, current=150)
    task = asyncio.ensure_future(_wait(hass, entity_id))
    await _settle()

    change(mock_volcano)
    mock_volcano.data_updated()
    await asyncio.sleep(GRACE / 4)
    assert not task.done()
    mock_volcano.connected = True
    mock_volcano.data.heater = True
    mock_volcano.data_updated()

    # Well past the grace period: the blip was forgotten once it ended.
    await asyncio.sleep(GRACE * 2)
    assert not task.done()

    mock_volcano.data.current_temp = 190
    mock_volcano.data_updated()
    assert await task == {"reached": True, "reason": None}


async def test_turn_on(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """With turn_on, a heater that is off is switched on before waiting."""
    entity_id = await _heating(hass, mock_volcano, current=150)
    mock_volcano.data.heater = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    task = asyncio.ensure_future(_wait(hass, entity_id, turn_on=True))
    await _settle()
    assert ("heater", True) in mock_volcano.commands
    assert not task.done()

    mock_volcano.data.heater = True
    mock_volcano.data.current_temp = 190
    mock_volcano.data_updated()
    assert await task == {"reached": True, "reason": None}


async def test_turn_on_leaves_a_heater_that_is_on_alone(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A heater that is already on gets no command."""
    entity_id = await _heating(hass, mock_volcano, current=190)

    assert await _wait(hass, entity_id, turn_on=True) == {
        "reached": True,
        "reason": None,
    }
    assert ("heater", True) not in mock_volcano.commands


async def test_no_tolerance_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Without a tolerance, a degree under the target is not reached."""
    entity_id = await _heating(hass, mock_volcano, current=189)

    assert await _wait(hass, entity_id, timeout=0.01) == {
        "reached": False,
        "reason": "timeout",
    }


async def test_failure_raises_without_a_response(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    short_grace: None,
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


async def test_temperature_is_set_first(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """With a temperature, the target is set before waiting for it."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    task = asyncio.ensure_future(_wait(hass, entity_id, temperature=200))
    await _settle()
    assert ("target_temperature", 200) in mock_volcano.commands
    assert not task.done()

    # The fake does not confirm writes on its own; the device would.
    mock_volcano.data.set_temp = 200
    mock_volcano.data.current_temp = 200
    mock_volcano.data_updated()
    assert await task == {"reached": True, "reason": None}


async def test_temperature_in_fahrenheit(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The temperature is taken in the configured unit, like climate's."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity_id = await _heating(hass, mock_volcano, current=200)

    # 392 °F is 200 °C, already reached.
    assert await _wait(hass, entity_id, temperature=392, timeout=0.01) is not None
    assert ("target_temperature", 200) in mock_volcano.commands


@pytest.mark.parametrize("temperature", [39, 231])
async def test_temperature_out_of_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
    temperature: int,
) -> None:
    """A target outside the device's range is refused before anything is sent."""
    entity_id = await _heating(hass, mock_volcano, current=150)

    with pytest.raises(ServiceValidationError) as err:
        await _wait(hass, entity_id, temperature=temperature, turn_on=True)
    assert err.value.translation_key == "temperature_out_of_range"
    assert mock_volcano.commands == []


async def test_highest_temperature_in_fahrenheit_is_accepted(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """446 °F, the maximum, converts to a hair over 230 °C and is still allowed."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity_id = await _heating(hass, mock_volcano, current=230)

    await _wait(hass, entity_id, temperature=446, timeout=0.01)
    assert ("target_temperature", 230) in mock_volcano.commands
