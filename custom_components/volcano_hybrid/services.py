"""Service actions for Storz & Bickel devices."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
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
DEFAULT_TOLERANCE = 1.0
DEFAULT_TIMEOUT = timedelta(minutes=15)

WAIT_FOR_TEMPERATURE_SCHEMA: dict[str | vol.Marker, Any] = {
    vol.Optional(ATTR_TOLERANCE, default=DEFAULT_TOLERANCE): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=20)
    ),
    vol.Optional(ATTR_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
        cv.time_period, cv.positive_timedelta
    ),
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
    Wait until the device reaches its target, less the tolerance.

    A caller that asks for a response gets the outcome as data, so a script can
    switch the device off when the wait fails; one that does not gets an error,
    so a failed wait never lets a script carry on as if it had heated up.
    """
    climate = cast("VolcanoHybridClimate", entity)
    tolerance = TemperatureConverter.convert_interval(
        call.data[ATTR_TOLERANCE],
        call.hass.config.units.temperature_unit,
        UnitOfTemperature.CELSIUS,
    )
    timeout: timedelta = call.data[ATTR_TIMEOUT]
    try:
        await climate.coordinator.async_wait_for_temperature(
            tolerance, timeout.total_seconds()
        )
    except TemperatureWaitError as err:
        if call.return_response:
            return {"reached": False, "reason": err.reason}
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=f"wait_{err.reason}",
        ) from err
    return {"reached": True, "reason": None}
