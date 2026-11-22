"""Integration for Volcano Hybrid BLE device."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_MODEL, DOMAIN
from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .services import async_setup_services
from .volcano_ble import DeviceFamily

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, once for every entry."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: VolcanoHybridConfigEntry
) -> bool:
    """Set up a Storz & Bickel device from a config entry."""
    coordinator = VolcanoHybridCoordinator(
        hass,
        config_entry=entry,
        address=entry.data[CONF_ADDRESS],
        family=DeviceFamily(entry.data[CONF_MODEL]),
    )
    entry.runtime_data = coordinator
    _async_migrate_unique_ids(hass, entry)

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


# Entity keys that were renamed, old -> new. Up to 1.2.0-alpha1 the Crafty's
# PRJSTAT2 bit 12 switch was called "Automatic Bluetooth shutdown" after the
# vendor app's mask name, though the app labels it "Permanent Bluetooth" and a
# set bit keeps Bluetooth on (#108).
RENAMED_KEYS: dict[str, str] = {"auto_ble_shutdown": "permanent_bluetooth"}


@callback
def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Move entities of renamed keys to their new unique ID.

    The entity ID, name overrides and history stay with the registry entry, so
    automations keep working. An entry is left alone if the new unique ID is
    already taken, which only happens after a downgrade and re-upgrade.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        address, _, key = entity.unique_id.rpartition("-")
        if (new_key := RENAMED_KEYS.get(key)) is None:
            continue
        new_unique_id = f"{address}-{new_key}"
        if registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id):
            continue
        registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Migrate old entries.

    Entries below minor version 2 predate family support and were only ever Volcano
    Hybrids. A major version above 1 comes from a newer release this one cannot
    read (a downgrade), and is refused.
    """
    if entry.version > 1:
        return False
    if entry.minor_version < 2:  # noqa: PLR2004
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_MODEL: DeviceFamily.VOLCANO_HYBRID.value},
            minor_version=2,
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
