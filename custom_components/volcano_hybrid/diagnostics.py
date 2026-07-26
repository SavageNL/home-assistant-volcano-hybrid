"""Diagnostics support for the Volcano Hybrid integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .coordinator import VolcanoHybridConfigEntry

TO_REDACT = {CONF_ADDRESS, "connected_addr", "serial_number"}


def _as_hex(value: int | None) -> str | None:
    """Format a status register the way the vendor app's report does."""
    if value is None:
        return None
    return f"0x{value:04x}"


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
                "auto_shutdown": data.auto_shutdown,
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
            # makes them worth attaching to a bug report.
            "registers": {
                "prj1": _as_hex(data.prj1),
                "prj2": _as_hex(data.prj2),
                "prj3": _as_hex(data.prj3),
                "hist1": data.hist1,
                "hist2": data.hist2,
            },
        },
        TO_REDACT,
    )
