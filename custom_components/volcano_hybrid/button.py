"""Support for Volcano sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

SENSOR_DESCRIPTIONS: dict[str, ButtonEntityDescription] = {
    VolcanoSensor.RECONNECT: ButtonEntityDescription(
        key=VolcanoSensor.RECONNECT,
        translation_key=VolcanoSensor.RECONNECT,
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Volcano BLE buttons."""
    coordinator = entry.runtime_data

    async def _async_reconnect() -> None:
        """Reconnect to the Volcano Hybrid."""
        await coordinator.reconnect()

    async_add_entities(
        [
            VolcanoButtonEntity(coordinator, VolcanoSensor.RECONNECT, _async_reconnect),
        ]
    )


class VolcanoButtonEntity(VolcanoHybridEntity, ButtonEntity):
    """Representation of a Volcano button."""

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        key: VolcanoSensor,
        async_callback: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, SENSOR_DESCRIPTIONS[key], always_available=True)
        self._async_on_click_callback = async_callback

    async def async_press(self) -> None:
        """Press the button."""
        await self._async_on_click_callback()
