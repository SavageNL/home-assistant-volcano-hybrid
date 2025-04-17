"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VolcanoHybridCoordinator
from .volcano_ble import VolcanoSensor

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    VolcanoSensor.CURRENT_AUTO_OFF_TIME: SensorEntityDescription(
        key=VolcanoSensor.CURRENT_AUTO_OFF_TIME,
        name="Auto off time",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    VolcanoSensor.HEAT_TIME: SensorEntityDescription(
        key=VolcanoSensor.HEAT_TIME,
        name="Total heat time",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Volcano BLE sensors."""
    coordinator: VolcanoHybridCoordinator = entry.runtime_data

    async_add_entities(
        [
            VolcanoSensorEntity(coordinator, VolcanoSensor.CURRENT_AUTO_OFF_TIME),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HEAT_TIME),
        ]
    )


class VolcanoSensorEntity(CoordinatorEntity, SensorEntity):
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
        self._attr_available = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        new_value = self.coordinator.data.get(self._key)
        self._attr_native_value = new_value
        self._attr_available = self.coordinator.data.available
        super()._handle_coordinator_update()
