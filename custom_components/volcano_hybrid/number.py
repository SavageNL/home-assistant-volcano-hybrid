"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

SENSOR_DESCRIPTIONS: dict[str, NumberEntityDescription] = {
    VolcanoSensor.SHUT_OFF: NumberEntityDescription(
        key=VolcanoSensor.SHUT_OFF,
        name="Shut off time",
        icon="mdi:timer-stop-outline",
        device_class=NumberDeviceClass.DURATION,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_max_value=360,
        native_min_value=0,
        native_step=30,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.LED_BRIGHTNESS: NumberEntityDescription(
        key=VolcanoSensor.LED_BRIGHTNESS,
        name="LED Brightness",
        icon="mdi:brightness-5",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_max_value=100,
        native_min_value=0,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE numbers."""
    coordinator = entry.runtime_data

    async_add_entities(
        [
            VolcanoNumberEntity(coordinator, VolcanoSensor.SHUT_OFF),
            VolcanoNumberEntity(coordinator, VolcanoSensor.LED_BRIGHTNESS),
        ]
    )


class VolcanoNumberEntity(VolcanoHybridEntity, NumberEntity):
    """Representation of a Volcano number."""

    def __init__(
        self, coordinator: VolcanoHybridCoordinator, key: VolcanoSensor
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, SENSOR_DESCRIPTIONS[key])

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await getattr(self.coordinator, "set_" + self._key)(value)
