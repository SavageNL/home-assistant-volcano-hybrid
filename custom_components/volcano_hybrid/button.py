"""Support for Volcano sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VolcanoHybridCoordinator
from .volcano_ble import VolcanoSensor

if TYPE_CHECKING:
    from collections.abc import Callable

SENSOR_DESCRIPTIONS: dict[str, ButtonEntityDescription] = {
    VolcanoSensor.RECONNECT: ButtonEntityDescription(
        key=VolcanoSensor.RECONNECT,
        name="(Re)connect",
        icon="mdi:bluetooth-connect",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_entity_name=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE sensors."""
    coordinator: VolcanoHybridCoordinator = entry.runtime_data

    async def _async_reconnect() -> None:
        """Reconnect to the Volcano Hybrid."""
        await coordinator.reconnect()

    async_add_entities(
        [
            VolcanoButtonEntity(coordinator, VolcanoSensor.RECONNECT, _async_reconnect),
        ]
    )


class VolcanoButtonEntity(ButtonEntity):
    """Representation of a Volcano button."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        async_callback: Callable,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SENSOR_DESCRIPTIONS[key]
        self._key = key
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_device_info = coordinator.device_info
        self._async_on_click_callback = async_callback

    async def async_press(self) -> None:
        """Press the button."""
        await self._async_on_click_callback()
