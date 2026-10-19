"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

SENSOR_DESCRIPTIONS: dict[str, NumberEntityDescription] = {
    VolcanoSensor.SHUT_OFF: NumberEntityDescription(
        key=VolcanoSensor.SHUT_OFF,
        translation_key=VolcanoSensor.SHUT_OFF,
        device_class=NumberDeviceClass.DURATION,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_max_value=360,
        # The vendor app's slider starts at 30 (spec §2); what a 0 s session
        # timer does to the device is untested.
        native_min_value=30,
        native_step=30,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.LED_BRIGHTNESS: NumberEntityDescription(
        key=VolcanoSensor.LED_BRIGHTNESS,
        translation_key=VolcanoSensor.LED_BRIGHTNESS,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_max_value=100,
        native_min_value=0,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.BOOST_TEMP: NumberEntityDescription(
        key=VolcanoSensor.BOOST_TEMP,
        translation_key=VolcanoSensor.BOOST_TEMP,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=1,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    VolcanoSensor.SUPERBOOST_TEMP: NumberEntityDescription(
        key=VolcanoSensor.SUPERBOOST_TEMP,
        translation_key=VolcanoSensor.SUPERBOOST_TEMP,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=1,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    VolcanoSensor.BRIGHTNESS: NumberEntityDescription(
        key=VolcanoSensor.BRIGHTNESS,
        translation_key=VolcanoSensor.BRIGHTNESS,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_min_value=1,
        native_max_value=9,
        native_step=1,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.AUTO_OFF_SECONDS: NumberEntityDescription(
        key=VolcanoSensor.AUTO_OFF_SECONDS,
        translation_key=VolcanoSensor.AUTO_OFF_SECONDS,
        device_class=NumberDeviceClass.DURATION,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=300,
        native_step=10,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
    ),
}


NUMBER_KEYS: tuple[VolcanoSensor, ...] = (
    VolcanoSensor.SHUT_OFF,
    VolcanoSensor.LED_BRIGHTNESS,
    VolcanoSensor.BOOST_TEMP,
    VolcanoSensor.AUTO_OFF_SECONDS,
    VolcanoSensor.SUPERBOOST_TEMP,
    VolcanoSensor.BRIGHTNESS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers the device family supports."""
    coordinator = entry.runtime_data
    capabilities = coordinator.data.capabilities
    async_add_entities(
        VolcanoNumberEntity(coordinator, key)
        for key in NUMBER_KEYS
        if key in capabilities
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
