"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

SENSOR_DESCRIPTIONS: dict[str, BinarySensorEntityDescription] = {
    VolcanoSensor.AT_TEMPERATURE: BinarySensorEntityDescription(
        key=VolcanoSensor.AT_TEMPERATURE,
        translation_key=VolcanoSensor.AT_TEMPERATURE,
        entity_registry_enabled_default=True,
    ),
    VolcanoSensor.HEATER_ACTIVE: BinarySensorEntityDescription(
        key=VolcanoSensor.HEATER_ACTIVE,
        translation_key=VolcanoSensor.HEATER_ACTIVE,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.HEAT,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.PUMP_ACTIVE: BinarySensorEntityDescription(
        key=VolcanoSensor.PUMP_ACTIVE,
        translation_key=VolcanoSensor.PUMP_ACTIVE,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.ACTUATOR_FAULT: BinarySensorEntityDescription(
        key=VolcanoSensor.ACTUATOR_FAULT,
        translation_key=VolcanoSensor.ACTUATOR_FAULT,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.AUTO_SHUTDOWN: BinarySensorEntityDescription(
        key=VolcanoSensor.AUTO_SHUTDOWN,
        translation_key=VolcanoSensor.AUTO_SHUTDOWN,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # The service/burn-in mode drives the device to 230 °C for ten minutes on
    # its own, so it is a problem to be told about rather than a mode to show.
    VolcanoSensor.SERVICE_MODE: BinarySensorEntityDescription(
        key=VolcanoSensor.SERVICE_MODE,
        translation_key=VolcanoSensor.SERVICE_MODE,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    # Two settings the device holds in PRJSTAT1. They are plain state flags,
    # not conditions: no device class fits either, and neither is written here.
    VolcanoSensor.AIR_STEP_MODE: BinarySensorEntityDescription(
        key=VolcanoSensor.AIR_STEP_MODE,
        translation_key=VolcanoSensor.AIR_STEP_MODE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.SECOND_STAGE: BinarySensorEntityDescription(
        key=VolcanoSensor.SECOND_STAGE,
        translation_key=VolcanoSensor.SECOND_STAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.PRV1_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV1_ERROR,
        translation_key=VolcanoSensor.PRV1_ERROR,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.PRV2_ERROR: BinarySensorEntityDescription(
        key=VolcanoSensor.PRV2_ERROR,
        translation_key=VolcanoSensor.PRV2_ERROR,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CONNECTED: BinarySensorEntityDescription(
        key=VolcanoSensor.CONNECTED,
        translation_key=VolcanoSensor.CONNECTED,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Volcano BLE binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.AT_TEMPERATURE),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.HEATER_ACTIVE),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.PUMP_ACTIVE),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.ACTUATOR_FAULT),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.AUTO_SHUTDOWN),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.SERVICE_MODE),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.AIR_STEP_MODE),
            VolcanoBinarySensorEntity(coordinator, VolcanoSensor.SECOND_STAGE),
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


class VolcanoBinarySensorEntity(VolcanoHybridEntity, BinarySensorEntity):
    """Representation of a Volcano binary sensor."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        *,
        always_available: bool = False,
        initial_value: bool | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator, SENSOR_DESCRIPTIONS[key], always_available=always_available
        )
        self._attr_is_on = initial_value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()
