"""Fixtures for the Volcano Hybrid tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_hybrid.const import DOMAIN

from . import VOLCANO_ADDRESS, VOLCANO_NAME, FakeVolcanoBLE

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the integration from actually being set up."""
    with patch(
        "custom_components.volcano_hybrid.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_volcano() -> Generator[FakeVolcanoBLE]:
    """Replace the VolcanoBLE device with an in-memory fake."""
    fake = FakeVolcanoBLE()
    with patch(
        "custom_components.volcano_hybrid.coordinator.VolcanoBLE",
        side_effect=fake.attach,
    ):
        yield fake


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Ensure all entities are enabled in the entity registry."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_volcano: FakeVolcanoBLE,
    enable_bluetooth: None,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration with a mocked Volcano device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=VOLCANO_ADDRESS,
        data={CONF_ADDRESS: VOLCANO_ADDRESS},
        title=VOLCANO_NAME,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    yield entry

    if entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
