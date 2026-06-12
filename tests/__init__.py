"""Tests for the Volcano Hybrid integration."""

from __future__ import annotations

import time

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth.models import BluetoothServiceInfoBleak

VOLCANO_ADDRESS = "AA:BB:CC:DD:EE:FF"
VOLCANO_NAME = "S&B VOLCANO H 123456"
STORZ_BICKEL_MANUFACTURER_ID = 1736


def make_service_info(
    address: str = VOLCANO_ADDRESS,
    name: str = VOLCANO_NAME,
    manufacturer_id: int = STORZ_BICKEL_MANUFACTURER_ID,
) -> BluetoothServiceInfoBleak:
    """Build the discovery info for a BLE device, a Volcano by default."""
    device = BLEDevice(address=address, name=name, details={"source": "local"})
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
