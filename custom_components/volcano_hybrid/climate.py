"""Climate entity for Volcano Hybrid BLE device."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    FAN_OFF,
    FAN_ON,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import VOLCANO_HYBRID_MAX_TEMP, VOLCANO_HYBRID_MIN_DISPLAY_TEMP
from .coordinator import VolcanoHybridConfigEntry, VolcanoHybridCoordinator
from .entity import VolcanoHybridEntity
from .volcano_ble import VolcanoSensor

PARALLEL_UPDATES = 0

SENSOR_DESCRIPTIONS: dict[str, ClimateEntityDescription] = {
    VolcanoSensor.VOLCANO: ClimateEntityDescription(
        key=VolcanoSensor.VOLCANO,
        name=None,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VolcanoHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity for Volcano Hybrid."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            VolcanoHybridClimate(coordinator, VolcanoSensor.VOLCANO),
        ]
    )


class VolcanoHybridClimate(VolcanoHybridEntity, ClimateEntity):
    """Representation of a Volcano Hybrid climate."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_fan_modes = [FAN_OFF, FAN_ON]
    _attr_min_temp = VOLCANO_HYBRID_MIN_DISPLAY_TEMP
    _attr_max_temp = VOLCANO_HYBRID_MAX_TEMP
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: VolcanoHybridCoordinator, key: str) -> None:
        """Initialize the climate."""
        super().__init__(coordinator, SENSOR_DESCRIPTIONS[key])
        # Seed from the coordinator instead of inventing values: the entity
        # writes its first state before the first coordinator update, so made
        # up defaults end up in the recorder as if they were readings.
        self._update_attrs()

    def _update_attrs(self) -> None:
        """Reflect the coordinator data on the entity attributes."""
        data = self.coordinator.data
        self._attr_current_temperature = data.current_temp
        self._attr_target_temperature = data.set_temp_state
        self._attr_assumed_state = data.is_assumed

        # None means "not read from the device yet", which is reported as
        # unknown rather than claiming the device is off.
        heater_state = data.heater_state
        if heater_state is None:
            self._attr_hvac_mode = None
        else:
            self._attr_hvac_mode = HVACMode.HEAT if heater_state else HVACMode.OFF

        fan_state = data.fan_state
        if fan_state is None:
            self._attr_fan_mode = None
        else:
            self._attr_fan_mode = FAN_ON if fan_state else FAN_OFF

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        super()._handle_coordinator_update()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        await self.coordinator.set_target_temperature(kwargs[ATTR_TEMPERATURE])

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        await self.coordinator.set_heater(hvac_mode == HVACMode.HEAT)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        await self.coordinator.set_fan(fan_mode == FAN_ON)
