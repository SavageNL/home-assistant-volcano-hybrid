"""Integration for Volcano Hybrid BLE device."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import VolcanoHybridCoordinator

PLATFORMS = ["binary_sensor", "climate", "number", "sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Volcano Hybrid from a config entry."""
    address = entry.data["address"]
    coordinator = entry.runtime_data = VolcanoHybridCoordinator(
        hass,
        config_entry=entry,
        address=address,
    )
    await coordinator.async_config_entry_first_refresh()

    # Forward entry setups to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
