"""Integration for Volcano Hybrid BLE device."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: VolcanoHybridConfigEntry
) -> bool:
    """Set up Volcano Hybrid from a config entry."""
    coordinator = VolcanoHybridCoordinator(
        hass,
        config_entry=entry,
        address=entry.data[CONF_ADDRESS],
    )
    entry.runtime_data = coordinator

    # Register the advertisement callback without blocking on a connect. The
    # connect below can stall at cold boot until the Bluetooth transport is
    # ready; awaiting it here would gate the whole HA startup on this entry.
    await coordinator.async_register_callbacks()

    # Entities read coordinator.data, which is already initialised in the
    # coordinator's __init__, so bring them up immediately.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Do the first connect in the background so startup is never gated on BLE.
    # The advertisement callback registered above reconnects on its own if the
    # device is out of range now.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}_first_refresh"
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VolcanoHybridConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    device: dr.DeviceEntry,
) -> bool:
    """Allow removing devices that no longer match the configured address."""
    address = entry.data[CONF_ADDRESS]
    return (DOMAIN, address) not in device.identifiers and (
        dr.CONNECTION_BLUETOOTH,
        address,
    ) not in device.connections
