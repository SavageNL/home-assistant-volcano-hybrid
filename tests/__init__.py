"""Tests for the Volcano Hybrid integration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_hybrid.const import DOMAIN
from custom_components.volcano_hybrid.volcano_ble.volcano_hybrid_data import (
    VolcanoHybridData,
    VolcanoHybridDataStatusProvider,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

VOLCANO_ADDRESS = "AA:BB:CC:DD:EE:FF"
VOLCANO_NAME = "S&B VOLCANO H 123456"
STORZ_BICKEL_MANUFACTURER_ID = 1736


def make_service_info(
    address: str = VOLCANO_ADDRESS,
    name: str = VOLCANO_NAME,
    manufacturer_id: int = STORZ_BICKEL_MANUFACTURER_ID,
) -> BluetoothServiceInfoBleak:
    """Build the discovery info for a BLE device, a Volcano by default."""
    device = make_ble_device(address=address, name=name)
    advertisement = AdvertisementData(
        local_name=name,
        manufacturer_data={manufacturer_id: b""},
        service_data={},
        service_uuids=[],
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
        service_uuids=[],
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


class FakeVolcanoBLE(VolcanoHybridDataStatusProvider):
    """In-memory stand-in for the VolcanoBLE device used by the coordinator."""

    def __init__(self) -> None:
        """Initialize the fake device."""
        self.data = VolcanoHybridData(self)
        self.data_updated: Callable[[], None] = lambda: None
        self.device_updated: Callable[[], None] = lambda: None
        self.device_rssi: int | None = -60
        self.connected = False
        self.write_result = True
        self.error: Exception | None = None
        self.commands: list[tuple[str, Any]] = []
        self.disconnect_count = 0
        self.manual_update_count = 0

    def attach(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
    ) -> FakeVolcanoBLE:
        """Attach the coordinator callbacks, mimicking the constructor."""
        self.data_updated = data_updated
        self.device_updated = device_updated
        return self

    @property
    def rssi(self) -> int | None:
        """Get the device rssi."""
        return self.device_rssi

    @property
    def is_connected(self) -> bool:
        """Determine whether the device is connected."""
        return self.connected

    @property
    def connected_addr(self) -> str | None:
        """Get the connected adapter address."""
        return "hci0" if self.connected else None

    async def async_manual_update(self, device: BLEDevice) -> VolcanoHybridData:
        """Record a manual update."""
        self.manual_update_count += 1
        return self.data

    async def async_disconnect(self) -> None:
        """Record a disconnect."""
        self.disconnect_count += 1
        self.connected = False

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
