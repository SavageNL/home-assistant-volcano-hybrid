"""Sensors for Volcano Hybrid BLE device."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VolcanoHybridCoordinator
from .volcano_ble import VolcanoSensor

SENSOR_DESCRIPTIONS: dict[str, ClimateEntityDescription] = {
    VolcanoSensor.VOLCANO: ClimateEntityDescription(
        key=VolcanoSensor.VOLCANO,
        name=None,
        has_entity_name=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for Volcano Hybrid."""
    coordinator: VolcanoHybridCoordinator = config_entry.runtime_data
    async_add_entities(
        [
            VolcanyHybridClimate(coordinator, "volcano"),
        ]
    )


class VolcanyHybridClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Volcano Hybrid climate."""

    def __init__(self, coordinator: VolcanoHybridCoordinator, key: str) -> None:
        """Initialize the climate."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = SENSOR_DESCRIPTIONS[key]
        self._key = key
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_device_info = coordinator.device_info

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_fan_modes = ["off", "on"]
        self._attr_swing_modes = []
        self._attr_min_temp = 40
        self._attr_max_temp = 230
        self._attr_target_temperature_step = 1
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

        self._attr_current_temperature = 0
        self._attr_target_temperature = 40
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = "off"

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_current_temperature = self.coordinator.data.current_temp
        self._attr_target_temperature = self.coordinator.data.set_temp
        self._attr_hvac_mode = (
            HVACMode.HEAT if self.coordinator.data.heater else HVACMode.OFF
        )
        self._attr_fan_mode = "on" if self.coordinator.data.fan else "off"
        super()._handle_coordinator_update()

    async def async_set_temperature(self, **kwargs: any) -> None:
        """Set the HVAC mode."""
        await self.coordinator.set_target_temperature(kwargs["temperature"])

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        await self.coordinator.set_heater(hvac_mode == HVACMode.HEAT)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the HVAC mode."""
        await self.coordinator.set_fan(fan_mode == "on")
