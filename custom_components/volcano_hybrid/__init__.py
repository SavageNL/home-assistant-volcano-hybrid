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
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
