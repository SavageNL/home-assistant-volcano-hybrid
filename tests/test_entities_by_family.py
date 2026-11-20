"""One test per family pinning the exact entity set it creates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_hybrid.volcano_ble import DeviceFamily

from . import VOLCANO_ADDRESS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

# Platform -> keys. A key here is `{address}-{key}`'s key part. Extend the
# family's block when a task adds an entity; a leak from another family fails.
GOLDEN_ENTITIES: dict[DeviceFamily, dict[str, set[str]]] = {
    DeviceFamily.VOLCANO_HYBRID: {
        "climate": {"volcano"},
        "number": {"shut_off", "led_brightness"},
        "switch": {
            "showing_celsius",
            "display_on_cooling",
            "vibration",
            "auto_connect",
        },
        "sensor": {
            "current_auto_off_time",
            "current_on_time",
            "heat_time",
            "rssi",
            "connected_addr",
            "mains_voltage",
            "prj1",
            "prj2",
            "prj3",
            "prj4",
            "prj5",
            "hist1",
            "hist2",
            "last_fault",
        },
        "binary_sensor": {
            "at_temperature",
            "heater",
            "fan",
            "actuator_fault",
            "auto_shutdown",
            "service_mode",
            "prv1_error",
            "prv2_error",
            "connected",
        },
        "button": {"reconnect", "delayed_reconnect"},
        "update": {"firmware"},
    },
    DeviceFamily.CRAFTY: {
        "climate": {"volcano"},
        "number": {"boost_temp", "led_brightness", "auto_off_seconds"},
        "switch": {"vibration", "charge_led", "auto_ble_shutdown", "auto_connect"},
        "sensor": {
            "battery",
            "auto_off_countdown",
            "heat_time",
            "rssi",
            "connected_addr",
            "prj1",
            "prj2",
            "system_status",
            "battery_status1",
            "battery_status2",
        },
        "binary_sensor": {
            "at_temperature",
            "heater",
            "boost_mode",
            "superboost_mode",
            "error",
            "needs_factory_reset",
            "find_mode",
            "charging",
            "connected",
        },
        "button": {"reconnect", "delayed_reconnect", "find_device"},
    },
    DeviceFamily.VENTY: {
        "climate": {"volcano"},
        "number": {"boost_temp", "superboost_temp", "brightness"},
        "switch": {
            "showing_celsius",
            "vibration",
            "charge_optimization",
            "charge_limit",
            "boost_visualization",
            "boost_timeout_disabled",
            "auto_connect",
        },
        "sensor": {
            "battery",
            "auto_off_countdown",
            "heater_mode",
            "heat_time",
            "charging_time",
            "rssi",
            "connected_addr",
        },
        "binary_sensor": {
            "at_temperature",
            "heater",
            "charging",
            "boost_mode",
            "superboost_mode",
            "target_changed_on_device",
            "bootloader_mode",
            "permanent_bluetooth_enabled",
            "connected",
        },
        "button": {"reconnect", "delayed_reconnect", "find_device"},
        "update": {"firmware"},
    },
    DeviceFamily.VEAZY: {
        "climate": {"volcano"},
        "number": {"boost_temp", "superboost_temp", "brightness"},
        "switch": {
            "showing_celsius",
            "vibration",
            "charge_optimization",
            "charge_limit",
            "boost_visualization",
            "boost_timeout_disabled",
            "permanent_bluetooth",
            "auto_connect",
        },
        "sensor": {
            "battery",
            "auto_off_countdown",
            "heater_mode",
            "heat_time",
            "charging_time",
            "color",
            "rssi",
            "connected_addr",
        },
        "binary_sensor": {
            "at_temperature",
            "heater",
            "charging",
            "boost_mode",
            "superboost_mode",
            "target_changed_on_device",
            "bootloader_mode",
            "connected",
        },
        "button": {"reconnect", "delayed_reconnect", "find_device"},
        "update": {"firmware"},
    },
}


@pytest.mark.parametrize("device_family", list(GOLDEN_ENTITIES), indirect=True, ids=str)
async def test_entity_set_per_family(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    device_family: DeviceFamily,
) -> None:
    """Exactly the golden entities exist for the family, no more, no fewer."""
    registry = er.async_get(hass)
    created: dict[str, set[str]] = {}
    for entry in er.async_entries_for_config_entry(registry, init_integration.entry_id):
        assert entry.unique_id.startswith(f"{VOLCANO_ADDRESS}-")
        created.setdefault(entry.domain, set()).add(
            entry.unique_id.removeprefix(f"{VOLCANO_ADDRESS}-")
        )
    assert created == GOLDEN_ENTITIES[device_family]
