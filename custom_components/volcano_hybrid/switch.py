"""Support for Volcano switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

SENSOR_DESCRIPTIONS: dict[str, SwitchEntityDescription] = {
    VolcanoSensor.SHOWING_CELSIUS: SwitchEntityDescription(
        key=VolcanoSensor.SHOWING_CELSIUS,
        name="Showing celsius",
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
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            VolcanoSwitchEntity(coordinator, VolcanoSensor.SHOWING_CELSIUS),
            VolcanoSwitchEntity(coordinator, VolcanoSensor.DISPLAY_ON_COOLING),
            VolcanoSwitchEntity(coordinator, VolcanoSensor.VIBRATION),
        ]
    )


class VolcanoSwitchEntity(VolcanoHybridEntity, SwitchEntity):
    """Representation of a Volcano switch."""

    def __init__(
        self, coordinator: VolcanoHybridCoordinator, key: VolcanoSensor
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, SENSOR_DESCRIPTIONS[key])

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.get(self._key)
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await getattr(self.coordinator, "set_" + self._key)(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await getattr(self.coordinator, "set_" + self._key)(False)
