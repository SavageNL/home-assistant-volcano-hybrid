"""Diagnostics support for the Volcano Hybrid integration."""

from __future__ import annotations

import inspect
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import format_register
from .coordinator import VolcanoHybridConfigEntry
from .volcano_ble import VolcanoHybridData
from .volcano_ble.crafty_data import CraftyData

TO_REDACT = {CONF_ADDRESS, "connected_addr", "serial_number"}

# Reported under their own keys, or not state at all.
_NOT_STATE = {
    "device",
    "capabilities",
    "serial_number",
    "model",
    "model_name",
    "mains_voltage",
    "firmware",
    "firmware_version",
    "firmware_ble_version",
    "bootloader_version",
    "connected",
    "connected_addr",
    "rssi",
    "prj1",
    "prj2",
    "prj3",
    "prj4",
    "prj5",
    "hist1",
    "hist2",
    "system_status",
    "battery_status1",
    "battery_status2",
}
_PLAIN = (str, int, float, bool, type(None))


def _state(data: object) -> dict[str, Any]:
    """Every plain value the data object holds, whatever the device family."""
    names = {
        name
        for name, member in inspect.getmembers(type(data))
        if isinstance(member, property)
    } | set(vars(data))
    return {
        name: value
        for name in sorted(names)
        if not name.startswith("_")
        and name not in _NOT_STATE
        # Exact types only: enums subclass str/int but are not JSON-plain.
        and type(value := getattr(data, name)) in _PLAIN
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VolcanoHybridConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    diagnostics: dict[str, Any] = {
        "entry_data": dict(entry.data),
        "device": {
            "serial_number": data.serial_number,
            # The device's own identity strings, read verbatim: what it
            # calls itself and which mains it was built for. Families that
            # do not report one read null.
            "model": getattr(data, "model", None),
            "mains_voltage": getattr(data, "mains_voltage", None),
            "firmware": getattr(data, "firmware", None),
            "firmware_version": data.firmware_version,
            "firmware_ble_version": data.firmware_ble_version,
            "bootloader_version": data.bootloader_version,
        },
        "connection": {
            "connected": data.connected,
            "connected_addr": data.connected_addr,
            "rssi": data.rssi,
        },
        "state": _state(data),
    }
    if isinstance(data, VolcanoHybridData):
        # The raw status registers and error history, as read by the vendor
        # app's "Analysis" report. Undecoded on purpose: these carry the
        # bits the integration does not interpret, which is exactly what
        # makes them worth attaching to a bug report. prj4 and prj5 go
        # beyond that report — they are the controller's other two status
        # words, and read null on any device that does not serve them.
        diagnostics["registers"] = {
            "prj1": format_register(data.prj1),
            "prj2": format_register(data.prj2),
            "prj3": format_register(data.prj3),
            "prj4": format_register(data.prj4),
            "prj5": format_register(data.prj5),
            "hist1": data.hist1,
            "hist2": data.hist2,
        }
    elif isinstance(data, CraftyData):
        # The Crafty's raw status words (CRAFTY_BLE_SPEC.md), for the same
        # reason: they hold the bits the integration does not decode.
        diagnostics["registers"] = {
            "prj1": format_register(data.prj1),
            "prj2": format_register(data.prj2),
            "system_status": format_register(data.system_status),
            "battery_status1": format_register(data.battery_status1),
            "battery_status2": format_register(data.battery_status2),
        }
    if extended := await entry.runtime_data.async_read_extended_diagnostics():
        # Values only community clients read (CRAFTY_BLE_SPEC.md §4.4), raw
        # and read just now, so a download is how they get confirmed. Null
        # where the device does not serve one, or is not connected.
        diagnostics["extended"] = extended
    # The whole service table with each characteristic's properties: which
    # ones can notify, and any the specs do not document. Last because it is
    # long; empty when the device is not connected.
    diagnostics["gatt"] = entry.runtime_data.gatt_table()
    return async_redact_data(diagnostics, TO_REDACT)
