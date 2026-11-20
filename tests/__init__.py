"""Tests for the Volcano Hybrid integration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_hybrid.const import CONF_MODEL, DOMAIN
from custom_components.volcano_hybrid.volcano_ble import DATA_CLASSES, DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.volcano_hybrid_data import (
    VolcanoHybridDataStatusProvider,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

    from custom_components.volcano_hybrid.volcano_ble import VolcanoHybridData

VOLCANO_ADDRESS = "AA:BB:CC:DD:EE:FF"
VOLCANO_NAME = "S&B VOLCANO H 123456"
CRAFTY_NAME = "STORZ&BICKEL"
VENTY_NAME = "S&B VY123456"
VEAZY_NAME = "S&B VZ654321"
STORZ_BICKEL_MANUFACTURER_ID = 1736
FAMILY_NAMES: dict[DeviceFamily, str] = {
    DeviceFamily.VOLCANO_HYBRID: VOLCANO_NAME,
    DeviceFamily.CRAFTY: CRAFTY_NAME,
    DeviceFamily.VENTY: VENTY_NAME,
    DeviceFamily.VEAZY: VEAZY_NAME,
}


def make_service_info(
    address: str = VOLCANO_ADDRESS,
    name: str = VOLCANO_NAME,
    manufacturer_id: int = STORZ_BICKEL_MANUFACTURER_ID,
    service_uuids: list[str] | None = None,
) -> BluetoothServiceInfoBleak:
    """Build the discovery info for a BLE device, a Volcano by default."""
    device = make_ble_device(address=address, name=name)
    advertisement = AdvertisementData(
        local_name=name,
        manufacturer_data={manufacturer_id: b""},
        service_data={},
        service_uuids=service_uuids or [],
        tx_power=None,
        rssi=-60,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={manufacturer_id: b""},
        service_data={},
        service_uuids=service_uuids or [],
        source="local",
        device=device,
        advertisement=advertisement,
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )


def make_ble_device(
    address: str = VOLCANO_ADDRESS, name: str = VOLCANO_NAME
) -> BLEDevice:
    """Build a BLE device."""
    return BLEDevice(address=address, name=name, details={"source": "hci0"})


def get_entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Look up the entity id of one of the Volcano entities."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        platform, DOMAIN, f"{VOLCANO_ADDRESS}-{key}"
    )
    assert entity_id is not None, f"Entity {platform}/{key} not registered"
    return entity_id


def make_config_entry(
    family: DeviceFamily = DeviceFamily.VOLCANO_HYBRID,
    address: str = VOLCANO_ADDRESS,
) -> MockConfigEntry:
    """Build a configured entry for a device of the given family."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=address,
        data={CONF_ADDRESS: address, CONF_MODEL: family.value},
        title=FAMILY_NAMES[family],
        version=1,
        minor_version=2,
    )


class FakeDevice(VolcanoHybridDataStatusProvider):
    """In-memory stand-in for a device, used by the coordinator tests."""

    def __init__(self, family: DeviceFamily = DeviceFamily.VOLCANO_HYBRID) -> None:
        """Initialize the fake device."""
        self.family = family
        self.data: Any = DATA_CLASSES[family](self)
        self.data_updated: Callable[[], None] = lambda: None
        self.device_updated: Callable[[], None] = lambda: None
        self.device_rssi: int | None = -60
        self.connected = False
        self.write_result = True
        self.error: Exception | None = None
        self.commands: list[tuple[str, Any]] = []
        self.disconnect_count = 0
        self.manual_update_count = 0
        self.extended_diagnostics: dict[str, int | None] = {}
        self.gatt: dict[str, dict[str, list[str]]] = {}

    def attach(
        self,
        family: DeviceFamily,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
    ) -> FakeDevice:
        """Stand in for create_device()."""
        assert family is self.family
        self.data_updated = data_updated
        self.device_updated = device_updated
        return self

    @property
    def rssi(self) -> int | None:
        """Get the device rssi."""
        return self.device_rssi

    @rssi.setter
    def rssi(self, value: int) -> None:
        """Set the device rssi, as an advertisement does."""
        self.device_rssi = value

    @property
    def is_connected(self) -> bool:
        """Determine whether the device is connected."""
        return self.connected

    @property
    def connected_addr(self) -> str | None:
        """Get the connected adapter address."""
        return "hci0" if self.connected else None

    async def async_manual_update(
        self, device: BLEDevice | None = None
    ) -> VolcanoHybridData:
        """Record a manual update."""
        self.manual_update_count += 1
        return self.data

    async def async_disconnect(self) -> None:
        """Record a disconnect."""
        self.disconnect_count += 1
        self.connected = False

    async def async_read_extended_diagnostics(self) -> dict[str, int | None]:
        """Return the configured extra diagnostic values."""
        return dict(self.extended_diagnostics)

    def gatt_table(self) -> dict[str, dict[str, list[str]]]:
        """Return the configured service table."""
        return self.gatt

    def _command(self, name: str, value: Any) -> bool:
        """Record a command, raising or failing when configured to."""
        if self.error is not None:
            raise self.error
        self.commands.append((name, value))
        return self.write_result

    async def async_set_fan(self, on: bool) -> bool:
        """Set the fan on or off."""
        return self._command("fan", on)

    async def async_set_heater(self, on: bool) -> bool:
        """Set the heater on or off."""
        return self._command("heater", on)

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the target temperature."""
        return self._command("target_temperature", target)

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Set the toggle for showing Celsius."""
        return self._command("showing_celsius", on)

    async def async_set_display_on_cooling(self, on: bool) -> bool:
        """Set the toggle for display on cooling."""
        return self._command("display_on_cooling", on)

    async def async_set_vibration(self, on: bool) -> bool:
        """Set the toggle for vibration."""
        return self._command("vibration", on)

    async def async_set_shut_off(self, minutes: int) -> bool:
        """Set the shut off time in minutes."""
        return self._command("shut_off", minutes)

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness."""
        return self._command("led_brightness", brightness)

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Record the command."""
        return self._command("boost_temp", offset)

    async def async_set_superboost_temperature(self, offset: int) -> bool:
        """Record the command."""
        return self._command("superboost_temp", offset)

    async def async_set_auto_off_seconds(self, seconds: int) -> bool:
        """Record the command."""
        return self._command("auto_off_seconds", seconds)

    async def async_set_charge_led(self, on: bool) -> bool:
        """Record the command."""
        return self._command("charge_led", on)

    async def async_set_auto_ble_shutdown(self, on: bool) -> bool:
        """Record the command."""
        return self._command("auto_ble_shutdown", on)

    async def async_find_device(self) -> bool:
        """Record the command."""
        return self._command("find_device", None)

    async def async_set_charge_optimization(self, on: bool) -> bool:
        """Record the command."""
        return self._command("charge_optimization", on)

    async def async_set_charge_limit(self, on: bool) -> bool:
        """Record the command."""
        return self._command("charge_limit", on)

    async def async_set_boost_visualization(self, on: bool) -> bool:
        """Record the command."""
        return self._command("boost_visualization", on)

    async def async_set_boost_timeout_disabled(self, on: bool) -> bool:
        """Record the command."""
        return self._command("boost_timeout_disabled", on)

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Record the command."""
        return self._command("permanent_bluetooth", on)

    async def async_set_brightness(self, brightness: int) -> bool:
        """Record the command."""
        return self._command("brightness", brightness)


FakeVolcanoBLE = FakeDevice
