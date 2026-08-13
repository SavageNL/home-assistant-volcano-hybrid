"""Tests for the Volcano Hybrid integration setup."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_hybrid import async_remove_config_entry_device
from custom_components.volcano_hybrid.const import DOMAIN

from . import (
    VOLCANO_ADDRESS,
    VOLCANO_NAME,
    FakeVolcanoBLE,
    get_entity_id,
    make_ble_device,
    make_service_info,
)

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from homeassistant.core import HomeAssistant

    from custom_components.volcano_hybrid.volcano_ble import VolcanoHybridData

OTHER_ADDRESS = "11:22:33:44:55:66"

_DEVICE_PATCH = "homeassistant.components.bluetooth.async_ble_device_from_address"
_INFO_PATCH = "homeassistant.components.bluetooth.async_last_service_info"


async def test_setup_does_not_block_on_initial_connect(
    hass: HomeAssistant,
    mock_volcano: FakeVolcanoBLE,
    enable_bluetooth: None,
) -> None:
    """Setup returns immediately instead of awaiting the initial BLE connect."""
    release = asyncio.Event()

    async def blocking_update(device: BLEDevice) -> VolcanoHybridData:
        # Stand in for a cold-boot connect that has not resolved yet.
        await release.wait()
        mock_volcano.connected = True
        return mock_volcano.data

    mock_volcano.async_manual_update = blocking_update  # type: ignore[method-assign]

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=VOLCANO_ADDRESS,
        data={CONF_ADDRESS: VOLCANO_ADDRESS},
        title=VOLCANO_NAME,
    )
    entry.add_to_hass(hass)

    with (
        patch(_DEVICE_PATCH, return_value=make_ble_device()),
        patch(_INFO_PATCH, return_value=make_service_info()),
    ):
        # Would deadlock if setup awaited the connect; the timeout makes that a
        # clean failure instead of a hang.
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_setup(entry.entry_id)

        # The entry is up with entities present while the connect is still blocked.
        assert entry.state is ConfigEntryState.LOADED
        assert not mock_volcano.connected
        assert hass.states.get(get_entity_id(hass, "climate", "volcano")) is not None

        # Releasing the background connect lets it complete.
        release.set()
        await hass.async_block_till_done()
        assert mock_volcano.connected


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
    mock_volcano.data.model = "HYBRID"
    mock_volcano.data.firmware_version = "V01.23"
    mock_volcano.data.bootloader_version = "V00.90"
    mock_volcano.device_updated()
    await hass.async_block_till_done()

    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.serial_number == "VH123456"
    # The device reports the bare class; it is shown as the product name.
    assert device.model == "Volcano Hybrid"
    assert device.sw_version == "V01.23"
    assert device.hw_version == "V00.90"
    # The identifiers key the device; reading its model must not change them.
    assert device.identifiers == {(DOMAIN, VOLCANO_ADDRESS)}


async def test_device_registry_model_fallback(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device that never reports a model keeps the integration's own name."""
    mock_volcano.data.serial_number = "VH123456"
    mock_volcano.device_updated()
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.model == "Volcano Hybrid"


async def test_device_registry_model_rendering(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Another model class reads correctly; anything else is left to the name."""
    device_registry = dr.async_get(hass)

    mock_volcano.data.model = "MEDIC"
    mock_volcano.device_updated()
    await hass.async_block_till_done()

    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.model == "Volcano Medic"

    # A value that is not a plain word is not a class name, so it is not
    # dressed up as one.
    mock_volcano.data.model = "230VAC"
    mock_volcano.device_updated()
    await hass.async_block_till_done()

    device = device_registry.async_get_device({(DOMAIN, VOLCANO_ADDRESS)})
    assert device is not None
    assert device.model == "Volcano Hybrid"


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
