"""Support for Volcano sensors."""

from __future__ import annotations

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VolcanoHybridCoordinator
from .volcano_ble import VolcanoSensor

SENSOR_DESCRIPTIONS: dict[str, SwitchEntityDescription] = {
    VolcanoSensor.SHOWING_CELCIUS: SwitchEntityDescription(
        key=VolcanoSensor.SHOWING_CELCIUS,
        name="Showing celcius",
        icon="mdi:temperature-celsius",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.DISPLAY_ON_COOLING: SwitchEntityDescription(
        key=VolcanoSensor.DISPLAY_ON_COOLING,
        name="Display on when cooling",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.VIBRATION: SwitchEntityDescription(
        key=VolcanoSensor.VIBRATION,
        name="Vibration enabled",
        icon="mdi:vibrate",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
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
            VolcanoSwitchEntity(coordinator, VolcanoSensor.SHOWING_CELCIUS),
            VolcanoSwitchEntity(coordinator, VolcanoSensor.DISPLAY_ON_COOLING),
            VolcanoSwitchEntity(coordinator, VolcanoSensor.VIBRATION),
        ]
    )


class VolcanoSwitchEntity(CoordinatorEntity, SwitchEntity):
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
        self._attr_available = self.coordinator.data.available

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.get(self._key)
        self._attr_available = self.coordinator.data.available
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await getattr(self.coordinator, "set_" + self._key)(True)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await getattr(self.coordinator, "set_" + self._key)(False)
