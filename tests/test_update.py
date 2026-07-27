"""Tests for the Volcano Hybrid firmware update entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN

from custom_components.volcano_hybrid.firmware import (
    LATEST_KNOWN_FIRMWARE,
    format_firmware_version,
)

from . import FakeVolcanoBLE, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

RECORDED = format_firmware_version(LATEST_KNOWN_FIRMWARE)
OLDER = (LATEST_KNOWN_FIRMWARE[0], LATEST_KNOWN_FIRMWARE[1] - 1)


def _set_firmware(mock_volcano: FakeVolcanoBLE, version: str | None) -> None:
    """Report a firmware version from the device."""
    mock_volcano.data.firmware_version = version
    mock_volcano.data.firmware = version


async def test_up_to_date_device_reports_no_update(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device on the recorded firmware is off."""
    _set_firmware(mock_volcano, f"{RECORDED}.00.00")
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["installed_version"] == RECORDED
    assert state.attributes["latest_version"] == RECORDED


async def test_outdated_device_reports_an_update(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """A device behind the recorded firmware is on, and links to the app."""
    _set_firmware(mock_volcano, f"{format_firmware_version(OLDER)}.00.00")
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == format_firmware_version(OLDER)
    assert state.attributes["latest_version"] == RECORDED
    assert state.attributes["release_url"] == "https://app.storz-bickel.com/"


async def test_device_ahead_of_this_release_is_not_told_to_downgrade(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Firmware newer than this release knows about still reports no update."""
    newer = (LATEST_KNOWN_FIRMWARE[0], LATEST_KNOWN_FIRMWARE[1] + 1)
    _set_firmware(mock_volcano, f"{format_firmware_version(newer)}.00.00")
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["latest_version"] == format_firmware_version(newer)


async def test_unknown_before_the_device_reports_its_firmware(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """Nothing is claimed until the vaporizer has been read."""
    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_falls_back_to_the_other_firmware_characteristic(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """The second firmware string is used when the primary one is missing."""
    mock_volcano.data.firmware_version = None
    mock_volcano.data.firmware = f"{format_firmware_version(OLDER)}.00.00"
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == format_firmware_version(OLDER)


async def test_stays_available_while_disconnected(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_volcano: FakeVolcanoBLE,
) -> None:
    """An update notice is useless if it only shows while the device is on."""
    _set_firmware(mock_volcano, f"{format_firmware_version(OLDER)}.00.00")
    mock_volcano.connected = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    mock_volcano.connected = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "update", "firmware"))
    assert state is not None
    assert state.state == STATE_ON
