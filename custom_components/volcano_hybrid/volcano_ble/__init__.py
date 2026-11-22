"""Volcano BLE module for communicating with the device."""

from .const import DeviceFamily, VolcanoSensor, detect_family, is_supported
from .data import DeviceData
from .device import (
    CommandNotConfirmedError,
    StorzBickelDevice,
    UnsupportedCommandError,
)
from .families import DATA_CLASSES, DEVICE_CLASSES, create_device
from .fault_log import FAULT_OPTIONS
from .volcano_ble import VolcanoBLE, VolcanoDevice
from .volcano_hybrid_data import VolcanoHybridData

__all__ = [
    "DATA_CLASSES",
    "DEVICE_CLASSES",
    "FAULT_OPTIONS",
    "CommandNotConfirmedError",
    "DeviceData",
    "DeviceFamily",
    "StorzBickelDevice",
    "UnsupportedCommandError",
    "VolcanoBLE",
    "VolcanoDevice",
    "VolcanoHybridData",
    "VolcanoSensor",
    "create_device",
    "detect_family",
    "is_supported",
]
