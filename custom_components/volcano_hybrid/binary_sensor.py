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
        has_entity_name=True,
    ),
    VolcanoSensor.PRV1_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV1_ERROR,
        name="Prv1 error",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
        has_entity_name=True,
    ),
    VolcanoSensor.PRV2_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV2_ERROR,
        name="Prv2 error",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
        has_entity_name=True,
    ),
    VolcanoSensor.CONNECTED: BinarySensorEntityDescription(
        key=VolcanoSensor.CONNECTED,
        name="Connected",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=True,
        has_entity_name=True,
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
            VolcanoBinarySensorEntity(
                coordinator,
                VolcanoSensor.CONNECTED,
                always_available=True,
                initial_value=False,
            ),
        ]
    )


class VolcanoBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Volcano sensor."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        *,
        always_available: bool = False,
        initial_value: bool | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = SENSOR_DESCRIPTIONS[key]
        self._key = key
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_device_info = coordinator.device_info
        self._always_available = always_available
        self._attr_is_on = initial_value
        self._attr_attribution = "Data provided by Volcano Hybrid"

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._always_available or super().available
