"""Diagnostics support for the Volcano Hybrid integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import format_register
from .coordinator import VolcanoHybridConfigEntry

TO_REDACT = {CONF_ADDRESS, "connected_addr", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VolcanoHybridConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "device": {
                "serial_number": data.serial_number,
                # The device's own identity strings, read verbatim: what it
                # calls itself and which mains it was built for.
                "model": data.model,
                "mains_voltage": data.mains_voltage,
                "firmware": data.firmware,
                "firmware_version": data.firmware_version,
                "firmware_ble_version": data.firmware_ble_version,
                "bootloader_version": data.bootloader_version,
            },
            "connection": {
                "connected": data.connected,
                "connected_addr": data.connected_addr,
                "rssi": data.rssi,
            },
            "state": {
                "current_temp": data.current_temp,
                "set_temp": data.set_temp,
                "set_temp_state": data.set_temp_state,
                "heater": data.heater,
                "heater_state": data.heater_state,
                "fan": data.fan,
                "fan_state": data.fan_state,
                "is_assumed": data.is_assumed,
                "at_temperature": data.at_temperature,
                "is_heating": data.is_heating,
                "is_cooling": data.is_cooling,
                "auto_shutdown": data.auto_shutdown,
                "actuator_fault": data.actuator_fault,
                "service_mode": data.service_mode,
                "prv1_error": data.prv1_error,
                "prv2_error": data.prv2_error,
                "showing_celsius": data.showing_celsius,
                "display_on_cooling": data.display_on_cooling,
                "vibration": data.vibration,
                "shut_off": data.shut_off,
                "led_brightness": data.led_brightness,
                "current_auto_off_time": data.current_auto_off_time,
                "current_on_time": data.current_on_time,
                "heat_time": data.heat_time,
            },
            # The raw status registers and error history, as read by the vendor
            # app's "Analysis" report. Undecoded on purpose: these carry the
            # bits the integration does not interpret, which is exactly what
            # makes them worth attaching to a bug report. prj4 and prj5 go
            # beyond that report — they are the controller's other two status
            # words, and read null on any device that does not serve them.
            "registers": {
                "prj1": format_register(data.prj1),
                "prj2": format_register(data.prj2),
                "prj3": format_register(data.prj3),
                "prj4": format_register(data.prj4),
                "prj5": format_register(data.prj5),
                "hist1": data.hist1,
                "hist2": data.hist2,
            },
        },
        TO_REDACT,
    )
