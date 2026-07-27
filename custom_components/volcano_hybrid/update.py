"""Support for reporting outdated Volcano Hybrid firmware."""

from __future__ import annotations

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .firmware import (
    FIRMWARE_UPDATE_URL,
    format_firmware_version,
    latest_firmware_version,
    parse_firmware_version,
)
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

UPDATE_DESCRIPTION = UpdateEntityDescription(
    key=VolcanoSensor.FIRMWARE,
    translation_key=VolcanoSensor.FIRMWARE,
    entity_category=EntityCategory.CONFIG,
    device_class=UpdateDeviceClass.FIRMWARE,
    entity_registry_enabled_default=True,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Volcano firmware update entity."""
    async_add_entities([VolcanoUpdateEntity(entry.runtime_data)])


class VolcanoUpdateEntity(VolcanoHybridEntity, UpdateEntity):
    """Reports whether the vaporizer is running the newest known firmware."""

    # No install support. The bootloader is reachable over plain BLE and could
    # be driven from here; the reason it is not is risk, not capability, and it
    # is written up in CLAUDE.md. This entity reports and links, it does not act.
    _attr_release_url = FIRMWARE_UPDATE_URL

    def __init__(self, coordinator: VolcanoHybridCoordinator) -> None:
        """Initialize the update entity."""
        # Stays available while the vaporizer is off: firmware does not change
        # on its own, and an update notice nobody sees unless they are already
        # using the device would be pointless.
        super().__init__(coordinator, UPDATE_DESCRIPTION, always_available=True)

    @property
    def _installed(self) -> tuple[int, int] | None:
        """Return the firmware version the device reported, if any."""
        data = self.coordinator.data
        # firmware_version is the string surfaced as the device's sw_version and
        # is the one confirmed to track the vendor's published version numbers;
        # firmware only stands in when it is missing.
        return parse_firmware_version(data.firmware_version) or parse_firmware_version(
            data.firmware
        )

    @property
    def installed_version(self) -> str | None:
        """Return the firmware currently on the vaporizer."""
        installed = self._installed
        return None if installed is None else format_firmware_version(installed)

    @property
    def latest_version(self) -> str | None:
        """Return the newest firmware known to this release of the integration."""
        latest = latest_firmware_version(self._installed)
        return None if latest is None else format_firmware_version(latest)
