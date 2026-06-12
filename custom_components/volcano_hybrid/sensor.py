"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    VolcanoSensor.CURRENT_AUTO_OFF_TIME: SensorEntityDescription(
        key=VolcanoSensor.CURRENT_AUTO_OFF_TIME,
        translation_key=VolcanoSensor.CURRENT_AUTO_OFF_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    VolcanoSensor.CURRENT_ON_TIME: SensorEntityDescription(
        key=VolcanoSensor.CURRENT_ON_TIME,
        translation_key=VolcanoSensor.CURRENT_ON_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.HEAT_TIME: SensorEntityDescription(
        key=VolcanoSensor.HEAT_TIME,
        translation_key=VolcanoSensor.HEAT_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.RSSI: SensorEntityDescription(
        key=VolcanoSensor.RSSI,
        translation_key=VolcanoSensor.RSSI,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CONNECTED_ADDR: SensorEntityDescription(
        key=VolcanoSensor.CONNECTED_ADDR,
        translation_key=VolcanoSensor.CONNECTED_ADDR,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE sensors."""
    coordinator = entry.runtime_data

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


class VolcanoSensorEntity(VolcanoHybridEntity, SensorEntity):
    """Representation of a Volcano sensor."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        *,
        always_available: bool = False,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator, SENSOR_DESCRIPTIONS[key], always_available=always_available
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()
