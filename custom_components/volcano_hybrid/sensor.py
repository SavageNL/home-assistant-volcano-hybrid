"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
        has_entity_name=True,
    ),
    VolcanoSensor.CURRENT_ON_TIME: SensorEntityDescription(
        key=VolcanoSensor.CURRENT_ON_TIME,
        name="Current on time",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
        has_entity_name=True,
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
        has_entity_name=True,
    ),
    VolcanoSensor.RSSI: SensorEntityDescription(
        key=VolcanoSensor.RSSI,
        name="Signal strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CONNECTED_ADDR: SensorEntityDescription(
        key=VolcanoSensor.CONNECTED_ADDR,
        name="Connected address",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
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
            VolcanoSensorEntity(coordinator, VolcanoSensor.CURRENT_AUTO_OFF_TIME),
            VolcanoSensorEntity(coordinator, VolcanoSensor.CURRENT_ON_TIME),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HEAT_TIME),
            VolcanoSensorEntity(coordinator, VolcanoSensor.RSSI, always_available=True),
            VolcanoSensorEntity(
                coordinator, VolcanoSensor.CONNECTED_ADDR, always_available=True
            ),
        ]
    )


class VolcanoSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Volcano sensor."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        *,
        always_available: bool = False,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = SENSOR_DESCRIPTIONS[key]
        self._key = key
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_device_info = coordinator.device_info
        self._always_available = always_available
        self._attr_attribution = "Data provided by Volcano Hybrid"

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        new_value = self.coordinator.data.get(self._key)
        self._attr_native_value = new_value
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._always_available or super().available
