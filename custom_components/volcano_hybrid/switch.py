"""Support for Volcano switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

AUTO_CONNECT_DESCRIPTION = SwitchEntityDescription(
    key=VolcanoSensor.AUTO_CONNECT,
    translation_key=VolcanoSensor.AUTO_CONNECT,
    device_class=SwitchDeviceClass.SWITCH,
    entity_category=EntityCategory.CONFIG,
)

SENSOR_DESCRIPTIONS: dict[str, SwitchEntityDescription] = {
    VolcanoSensor.SHOWING_CELSIUS: SwitchEntityDescription(
        key=VolcanoSensor.SHOWING_CELSIUS,
        translation_key=VolcanoSensor.SHOWING_CELSIUS,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.DISPLAY_ON_COOLING: SwitchEntityDescription(
        key=VolcanoSensor.DISPLAY_ON_COOLING,
        translation_key=VolcanoSensor.DISPLAY_ON_COOLING,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.VIBRATION: SwitchEntityDescription(
        key=VolcanoSensor.VIBRATION,
        translation_key=VolcanoSensor.VIBRATION,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CHARGE_LED: SwitchEntityDescription(
        key=VolcanoSensor.CHARGE_LED,
        translation_key=VolcanoSensor.CHARGE_LED,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CHARGE_OPTIMIZATION: SwitchEntityDescription(
        key=VolcanoSensor.CHARGE_OPTIMIZATION,
        translation_key=VolcanoSensor.CHARGE_OPTIMIZATION,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.CHARGE_LIMIT: SwitchEntityDescription(
        key=VolcanoSensor.CHARGE_LIMIT,
        translation_key=VolcanoSensor.CHARGE_LIMIT,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.BOOST_VISUALIZATION: SwitchEntityDescription(
        key=VolcanoSensor.BOOST_VISUALIZATION,
        translation_key=VolcanoSensor.BOOST_VISUALIZATION,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    VolcanoSensor.BOOST_TIMEOUT_DISABLED: SwitchEntityDescription(
        key=VolcanoSensor.BOOST_TIMEOUT_DISABLED,
        translation_key=VolcanoSensor.BOOST_TIMEOUT_DISABLED,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    # Decides whether the device is reachable at all, so it is on by default.
    VolcanoSensor.PERMANENT_BLUETOOTH: SwitchEntityDescription(
        key=VolcanoSensor.PERMANENT_BLUETOOTH,
        translation_key=VolcanoSensor.PERMANENT_BLUETOOTH,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
}


SWITCH_KEYS: tuple[VolcanoSensor, ...] = (
    VolcanoSensor.SHOWING_CELSIUS,
    VolcanoSensor.DISPLAY_ON_COOLING,
    VolcanoSensor.VIBRATION,
    VolcanoSensor.CHARGE_LED,
    VolcanoSensor.CHARGE_OPTIMIZATION,
    VolcanoSensor.CHARGE_LIMIT,
    VolcanoSensor.BOOST_VISUALIZATION,
    VolcanoSensor.BOOST_TIMEOUT_DISABLED,
    VolcanoSensor.PERMANENT_BLUETOOTH,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches the device family supports."""
    coordinator = entry.runtime_data
    capabilities = coordinator.data.capabilities
    entities: list[SwitchEntity] = [
        VolcanoSwitchEntity(coordinator, key)
        for key in SWITCH_KEYS
        if key in capabilities
    ]
    if VolcanoSensor.AUTO_CONNECT in capabilities:
        entities.append(VolcanoAutoConnectSwitch(coordinator))
    async_add_entities(entities)


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


class VolcanoAutoConnectSwitch(VolcanoHybridEntity, SwitchEntity, RestoreEntity):
    """Switch that controls whether the integration connects on its own."""

    def __init__(self, coordinator: VolcanoHybridCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, AUTO_CONNECT_DESCRIPTION, always_available=True)

    async def async_added_to_hass(self) -> None:
        """Restore the last auto-connect setting and apply it."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        # Default to enabled (the integration's historical behavior).
        self.coordinator.auto_connect = (
            last_state is None or last_state.state == STATE_ON
        )
        self._attr_is_on = self.coordinator.auto_connect

    def _handle_coordinator_update(self) -> None:
        """Reflect the coordinator's auto-connect state."""
        self._attr_is_on = self.coordinator.auto_connect
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable automatic connecting."""
        await self.coordinator.async_set_auto_connect(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable automatic connecting."""
        await self.coordinator.async_set_auto_connect(enabled=False)
