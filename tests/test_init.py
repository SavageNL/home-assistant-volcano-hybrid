"""Tests for the Volcano Hybrid integration setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.volcano_hybrid import async_remove_config_entry_device
from custom_components.volcano_hybrid.const import DOMAIN

from . import VOLCANO_ADDRESS, FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

OTHER_ADDRESS = "11:22:33:44:55:66"


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The entry sets up, creates entities and disconnects on unload."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(get_entity_id(hass, "climate", "volcano")) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert mock_volcano.disconnect_count == 1


async def test_device_registry_info(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The device registry is updated with data read from the device."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.manufacturer == "Storz & Bickel"
    assert device.model == "Volcano Hybrid"
    assert device.serial_number is None

    mock_volcano.data.serial_number = "VH123456"
    mock_volcano.data.firmware_version = "V01.23"
    mock_volcano.data.bootloader_version = "V00.90"
    mock_volcano.device_updated()
    await hass.async_block_till_done()

    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.serial_number == "VH123456"
    assert device.sw_version == "V01.23"
    assert device.hw_version == "V00.90"


async def test_remove_config_entry_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Only devices that no longer match the configured address are removable."""
    entry = init_integration
    device_registry = dr.async_get(hass)

    current = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert current is not None
    assert not await async_remove_config_entry_device(hass, entry, current)

    stale = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, OTHER_ADDRESS)},
    )
    assert await async_remove_config_entry_device(hass, entry, stale)
