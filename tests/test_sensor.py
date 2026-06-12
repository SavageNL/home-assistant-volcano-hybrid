"""Tests for the Volcano Hybrid sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_sensors(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The sensors reflect the device data."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.current_auto_off_time = 20.0
    data.shut_off = 30
    data.heat_hours_changed = 2
    data.heat_minutes_changed = 30
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    auto_off = hass.states.get(get_entity_id(hass, "sensor", "current_auto_off_time"))
    assert auto_off is not None
    assert float(auto_off.state) == 20.0

    on_time = hass.states.get(get_entity_id(hass, "sensor", "current_on_time"))
    assert on_time is not None
    assert float(on_time.state) == 10.0

    # 150 minutes, displayed in the suggested unit (hours)
    heat_time = hass.states.get(get_entity_id(hass, "sensor", "heat_time"))
    assert heat_time is not None
    assert float(heat_time.state) == 2.5

    rssi = hass.states.get(get_entity_id(hass, "sensor", "rssi"))
    assert rssi is not None
    assert float(rssi.state) == -60

    connected_addr = hass.states.get(get_entity_id(hass, "sensor", "connected_addr"))
    assert connected_addr is not None
    assert connected_addr.state == "hci0"


async def test_sensor_availability(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Regular sensors become unavailable on disconnect, diagnostics stay."""
    auto_off_id = get_entity_id(hass, "sensor", "current_auto_off_time")
    rssi_id = get_entity_id(hass, "sensor", "rssi")

    mock_volcano.connected = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    auto_off = hass.states.get(auto_off_id)
    assert auto_off is not None
    assert auto_off.state == STATE_UNAVAILABLE
    rssi = hass.states.get(rssi_id)
    assert rssi is not None
    assert rssi.state != STATE_UNAVAILABLE

    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    auto_off = hass.states.get(auto_off_id)
    assert auto_off is not None
    assert auto_off.state != STATE_UNAVAILABLE
