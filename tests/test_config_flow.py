"""Tests for the Volcano Hybrid config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_hybrid.config_flow import VolcanoHybridConfigFlow
from custom_components.volcano_hybrid.const import (
    CONF_AUTO_CONNECT_DELAY,
    CONF_DELAYED_RECONNECT_DELAY,
    DOMAIN,
)

from . import VOLCANO_ADDRESS, VOLCANO_NAME, make_service_info

OTHER_ADDRESS = "11:22:33:44:55:66"
OTHER_NAME = "S&B VOLCANO H 654321"


def _patch_discovered(service_infos: list[BluetoothServiceInfoBleak]) -> Any:
    """Patch the devices the config flow discovers."""
    return patch(
        "custom_components.volcano_hybrid.config_flow.async_discovered_service_info",
        return_value=service_infos,
    )


def _volcano_entry(
    address: str = VOLCANO_ADDRESS, name: str = VOLCANO_NAME
) -> MockConfigEntry:
    """Build a configured Volcano entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=address,
        data={CONF_ADDRESS: address},
        title=name,
    )


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The user flow lists discovered devices and creates an entry."""
    with _patch_discovered([make_service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: VOLCANO_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == VOLCANO_NAME
    assert result["data"] == {CONF_ADDRESS: VOLCANO_ADDRESS}
    assert result["result"].unique_id == VOLCANO_ADDRESS
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_no_devices_found(hass: HomeAssistant) -> None:
    """The user flow aborts when nothing is discovered."""
    with _patch_discovered([]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_ignores_unsupported_devices(hass: HomeAssistant) -> None:
    """The user flow does not offer devices that are not a Volcano."""
    with _patch_discovered(
        [make_service_info(name="OTHER DEVICE", manufacturer_id=76)]
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_ignores_configured_devices(hass: HomeAssistant) -> None:
    """The user flow does not offer devices that are already configured."""
    _volcano_entry().add_to_hass(hass)

    with _patch_discovered([make_service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_bluetooth_flow_creates_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The bluetooth discovery flow confirms and creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == VOLCANO_NAME
    assert result["data"] == {CONF_ADDRESS: VOLCANO_ADDRESS}
    assert result["result"].unique_id == VOLCANO_ADDRESS
    assert len(mock_setup_entry.mock_calls) == 1


async def test_bluetooth_flow_not_supported(hass: HomeAssistant) -> None:
    """The bluetooth discovery flow aborts for devices that are not a Volcano."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=make_service_info(name="OTHER DEVICE", manufacturer_id=76),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_confirm_without_discovery(hass: HomeAssistant) -> None:
    """The confirm step aborts when there is no discovered device."""
    flow = VolcanoHybridConfigFlow()
    flow.hass = hass
    flow.flow_id = "test"
    flow.handler = DOMAIN

    result = await flow.async_step_bluetooth_confirm()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_bluetooth_flow_already_configured(hass: HomeAssistant) -> None:
    """The bluetooth discovery flow aborts for already configured devices."""
    _volcano_entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_to_new_device(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The reconfigure flow can point the entry at a different Volcano."""
    entry = _volcano_entry()
    entry.add_to_hass(hass)

    with _patch_discovered(
        [
            make_service_info(),
            make_service_info(address=OTHER_ADDRESS, name=OTHER_NAME),
        ]
    ):
        result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: OTHER_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_ADDRESS: OTHER_ADDRESS}
    assert entry.unique_id == OTHER_ADDRESS
    assert entry.title == OTHER_NAME


async def test_reconfigure_keeps_current_device(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The reconfigure flow offers the currently configured device."""
    entry = _volcano_entry()
    entry.add_to_hass(hass)

    with _patch_discovered([make_service_info()]):
        result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: VOLCANO_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_ADDRESS: VOLCANO_ADDRESS}
    assert entry.unique_id == VOLCANO_ADDRESS


async def test_reconfigure_ignores_other_entries_devices(
    hass: HomeAssistant,
) -> None:
    """The reconfigure flow does not offer devices of other entries."""
    entry = _volcano_entry()
    entry.add_to_hass(hass)
    _volcano_entry(address=OTHER_ADDRESS, name=OTHER_NAME).add_to_hass(hass)

    with _patch_discovered([make_service_info(address=OTHER_ADDRESS, name=OTHER_NAME)]):
        result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_options_flow(hass: HomeAssistant) -> None:
    """The options flow stores the connect-timing options."""
    entry = _volcano_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_AUTO_CONNECT_DELAY: 2.5, CONF_DELAYED_RECONNECT_DELAY: 15.0},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_AUTO_CONNECT_DELAY: 2.5,
        CONF_DELAYED_RECONNECT_DELAY: 15.0,
    }
