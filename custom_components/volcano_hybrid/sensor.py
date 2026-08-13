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
from .volcano_ble import FAULT_OPTIONS, VolcanoHybridData, VolcanoSensor

if TYPE_CHECKING:
    from collections.abc import Callable

PARALLEL_UPDATES = 0


def _unchanged(value: Any) -> Any:
    """Report the device value as it is stored."""
    return value


def _fault_log_attributes(data: VolcanoHybridData) -> dict[str, Any]:
    """
    Report the whole fault log next to the entry the state names.

    Both history characteristics are given raw as well as decoded. The raw text
    keeps the empty `00` slots the decode drops, and it is what a bug report
    needs about a device whose log this integration reads wrong: it is the only
    thing here that is the device's own answer rather than an interpretation of
    it (VOLCANO_BLE_SPEC.md §3.5).
    """
    return {
        "hist1": data.hist1,
        "hist2": data.hist2,
        "hist1_faults": data.hist1_faults,
        "hist2_faults": data.hist2_faults,
    }


@dataclass(frozen=True, kw_only=True)
class VolcanoSensorEntityDescription(SensorEntityDescription):
    """Describes a Volcano sensor, with how its device value is presented."""

    value_fn: Callable[[Any], Any] = _unchanged
    # Sensors that report more than a single value take the whole data object,
    # since what belongs in the attributes is rarely what the state is keyed on.
    attributes_fn: Callable[[VolcanoHybridData], dict[str, Any]] | None = None


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
    # The mains the device was built for, as it reports it ("230VAC"). A fixed
    # property of the hardware rather than anything measured, so it carries no
    # device class or unit — it is a string, not a voltage reading.
    VolcanoSensor.MAINS_VOLTAGE: VolcanoSensorEntityDescription(
        key=VolcanoSensor.MAINS_VOLTAGE,
        translation_key=VolcanoSensor.MAINS_VOLTAGE,
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
    # The same log, read instead of copied: the newest code the device logged,
    # as one of the fault codes the spec recovered from the firmware. An enum
    # rather than free text, so the state stays a stable key and only the
    # translation is English — and so a code no table entry covers becomes a
    # single `unknown_code` state instead of a value Home Assistant would
    # reject for not being one of the declared options.
    VolcanoSensor.LAST_FAULT: VolcanoSensorEntityDescription(
        key=VolcanoSensor.LAST_FAULT,
        translation_key=VolcanoSensor.LAST_FAULT,
        device_class=SensorDeviceClass.ENUM,
        options=FAULT_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        attributes_fn=_fault_log_attributes,
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
            VolcanoSensorEntity(coordinator, VolcanoSensor.MAINS_VOLTAGE),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ1),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ2),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ3),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ4),
            VolcanoSensorEntity(coordinator, VolcanoSensor.PRJ5),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HIST1),
            VolcanoSensorEntity(coordinator, VolcanoSensor.HIST2),
            VolcanoSensorEntity(coordinator, VolcanoSensor.LAST_FAULT),
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
        if (attributes_fn := self.entity_description.attributes_fn) is not None:
            self._attr_extra_state_attributes = attributes_fn(self.coordinator.data)
        super()._handle_coordinator_update()
