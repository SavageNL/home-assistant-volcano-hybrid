"""Service actions for Storz & Bickel devices."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import DOMAIN
from .coordinator import TemperatureWaitError

if TYPE_CHECKING:
    from homeassistant.core import ServiceResponse
    from homeassistant.helpers.entity import Entity

    from .climate import VolcanoHybridClimate

SERVICE_WAIT_FOR_TEMPERATURE = "wait_for_temperature"
ATTR_TOLERANCE = "tolerance"
ATTR_TIMEOUT = "timeout"
ATTR_TURN_ON = "turn_on"
ATTR_TEMPERATURE = "temperature"
DEFAULT_TOLERANCE = 0.0
DEFAULT_TIMEOUT = timedelta(minutes=15)

WAIT_FOR_TEMPERATURE_SCHEMA: dict[str | vol.Marker, Any] = {
    vol.Optional(ATTR_TEMPERATURE): vol.Coerce(float),
    vol.Optional(ATTR_TOLERANCE, default=DEFAULT_TOLERANCE): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=20)
    ),
    vol.Optional(ATTR_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
        cv.time_period, cv.positive_timedelta
    ),
    vol.Optional(ATTR_TURN_ON, default=False): cv.boolean,
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_WAIT_FOR_TEMPERATURE,
        entity_domain=CLIMATE_DOMAIN,
        schema=WAIT_FOR_TEMPERATURE_SCHEMA,
        func=_async_wait_for_temperature,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def _async_wait_for_temperature(
    entity: Entity, call: ServiceCall
) -> ServiceResponse:
    """
    Set the target and switch the heater on if asked, then wait for it.

    A caller that asks for a response gets the outcome as data, so a script can
    switch the device off when the wait fails; one that does not gets an error,
    so a failed wait never lets a script carry on as if it had heated up.
    """
    climate = cast("VolcanoHybridClimate", entity)
    unit = call.hass.config.units.temperature_unit
    tolerance = TemperatureConverter.convert_interval(
        call.data[ATTR_TOLERANCE], unit, UnitOfTemperature.CELSIUS
    )
    timeout: timedelta = call.data[ATTR_TIMEOUT]
    coordinator = climate.coordinator
    if (temperature := call.data.get(ATTR_TEMPERATURE)) is not None:
        await coordinator.set_target_temperature(
            _target_celsius(climate, temperature, unit)
        )
    if call.data[ATTR_TURN_ON] and coordinator.data.heater_state is not True:
        await coordinator.set_heater(True)
    try:
        await coordinator.async_wait_for_temperature(tolerance, timeout.total_seconds())
    except TemperatureWaitError as err:
        if call.return_response:
            return {"reached": False, "reason": err.reason}
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=f"wait_{err.reason}",
        ) from err
    return {"reached": True, "reason": None}


def _target_celsius(
    climate: VolcanoHybridClimate, temperature: float, unit: str
) -> float:
    """Convert a target in the configured unit to °C, within the entity's range."""
    celsius = TemperatureConverter.convert(temperature, unit, UnitOfTemperature.CELSIUS)
    # Rounded before comparing: 446 °F converts to a hair above 230 °C.
    if not climate.min_temp <= round(celsius, 1) <= climate.max_temp:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="temperature_out_of_range",
            translation_placeholders={
                "temperature": f"{temperature:g}",
                "min": _in_unit(climate.min_temp, unit),
                "max": _in_unit(climate.max_temp, unit),
                "unit": unit,
            },
        )
    return celsius


def _in_unit(celsius: float, unit: str) -> str:
    """Render a °C limit in the configured unit."""
    value = TemperatureConverter.convert(celsius, UnitOfTemperature.CELSIUS, unit)
    return f"{round(value):g}"
