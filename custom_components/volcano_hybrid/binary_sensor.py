"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VolcanoHybridCoordinator
from .volcano_ble import VolcanoSensor

SENSOR_DESCRIPTIONS: dict[str, BinarySensorEntityDescription] = {
    VolcanoSensor.AUTO_SHUTDOWN: BinarySensorEntityDescription(
        key=VolcanoSensor.AUTO_SHUTDOWN,
        name="Auto shutdown enabled",
        icon="mdi:power",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.PRV1_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV1_ERROR,
        name="Prv1 error",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.PRV2_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV2_ERROR,
        name="Prv2 error",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE sensors."""
    coordinator: VolcanoHybridCoordinator = entry.runtime_data
    async_add_entities(
        [
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.AUTO_SHUTDOWN),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.PRV1_ERROR),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.PRV2_ERROR),
        ]
    )


class VolcanoBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Volcano sensor."""

    def __init__(
        self, coordinator: VolcanoHybridCoordinator, key: VolcanoSensor
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = SENSOR_DESCRIPTIONS[key]
        self._key = key
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_device_info = coordinator.device_info

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()
