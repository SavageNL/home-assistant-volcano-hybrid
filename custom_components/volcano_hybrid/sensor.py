"""Support for Volcano sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import format_register
from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

if TYPE_CHECKING:
    from collections.abc import Callable

PARALLEL_UPDATES = 0


def _unchanged(value: Any) -> Any:
    """Report the device value as it is stored."""
    return value


@dataclass(frozen=True, kw_only=True)
class VolcanoSensorEntityDescription(SensorEntityDescription):
    """Describes a Volcano sensor, with how its device value is presented."""

    value_fn: Callable[[Any], Any] = _unchanged


SENSOR_DESCRIPTIONS: dict[str, VolcanoSensorEntityDescription] = {
    VolcanoSensor.CURRENT_AUTO_OFF_TIME: VolcanoSensorEntityDescription(
        key=VolcanoSensor.CURRENT_AUTO_OFF_TIME,
        translation_key=VolcanoSensor.CURRENT_AUTO_OFF_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    VolcanoSensor.CURRENT_ON_TIME: VolcanoSensorEntityDescription(
        key=VolcanoSensor.CURRENT_ON_TIME,
        translation_key=VolcanoSensor.CURRENT_ON_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.HEAT_TIME: VolcanoSensorEntityDescription(
        key=VolcanoSensor.HEAT_TIME,
        translation_key=VolcanoSensor.HEAT_TIME,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.RSSI: VolcanoSensorEntityDescription(
        key=VolcanoSensor.RSSI,
        translation_key=VolcanoSensor.RSSI,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CONNECTED_ADDR: VolcanoSensorEntityDescription(
        key=VolcanoSensor.CONNECTED_ADDR,
        translation_key=VolcanoSensor.CONNECTED_ADDR,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # The raw status words and the snapshots the device captured at its last
    # fault. They are undecoded on purpose: they carry the bits this
    # integration does not interpret, which is what makes them worth reading
    # when a fault has to be diagnosed. See VOLCANO_BLE_SPEC.md for the bit
    # maps. No device class or unit: these are bit fields, not measurements.
    VolcanoSensor.PRJ1: VolcanoSensorEntityDescription(
        key=VolcanoSensor.PRJ1,
        translation_key=VolcanoSensor.PRJ1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=format_register,
    ),
    VolcanoSensor.PRJ2: VolcanoSensorEntityDescription(
        key=VolcanoSensor.PRJ2,
        translation_key=VolcanoSensor.PRJ2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=format_register,
    ),
    VolcanoSensor.PRJ3: VolcanoSensorEntityDescription(
        key=VolcanoSensor.PRJ3,
        translation_key=VolcanoSensor.PRJ3,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=format_register,
    ),
    # The controller's other two status words. No bit in them is decoded, and
    # whether a device serves them at all is unverified: when the
    # characteristics are missing their value is simply never set, so these
    # read as unknown while every other entity carries on.
    VolcanoSensor.PRJ4: VolcanoSensorEntityDescription(
        key=VolcanoSensor.PRJ4,
        translation_key=VolcanoSensor.PRJ4,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=format_register,
    ),
    VolcanoSensor.PRJ5: VolcanoSensorEntityDescription(
        key=VolcanoSensor.PRJ5,
        translation_key=VolcanoSensor.PRJ5,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=format_register,
    ),
    VolcanoSensor.HIST1: VolcanoSensorEntityDescription(
        key=VolcanoSensor.HIST1,
        translation_key=VolcanoSensor.HIST1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.HIST2: VolcanoSensorEntityDescription(
        key=VolcanoSensor.HIST2,
        translation_key=VolcanoSensor.HIST2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ1),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ2),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ3),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ4),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ5),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HIST1),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HIST2),
        ]
    )


class VolcanoSensorEntity(VolcanoHybridEntity, SensorEntity):
    """Representation of a Volcano sensor."""

    entity_description: VolcanoSensorEntityDescription

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
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.data.get(self._key)
        )
        super()._handle_coordinator_update()
