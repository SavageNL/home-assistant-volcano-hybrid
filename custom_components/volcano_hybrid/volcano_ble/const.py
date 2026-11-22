"""Constants for the VolcanoBLE."""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from habluetooth import BluetoothServiceInfoBleak

VOLCANO_HYBRID_MIN_TEMP = 0
VOLCANO_HYBRID_MAX_TEMP = 230

# The block temperature below which the device blanks its display again after
# the heater is switched off, used to decide when a cooldown has ended. The
# device does not report the state of its display, so this cannot be read back
# and is not measured here: it is what owners observe, and it lines up with the
# lowest temperature the device can be set to. Kept separate from that limit
# anyway, because they are two different facts that happen to share a value.
VOLCANO_HYBRID_DISPLAY_OFF_TEMP = 40


class DeviceFamily(StrEnum):
    """The Storz & Bickel device families this integration speaks to."""

    VOLCANO_HYBRID = "volcano_hybrid"
    # Crafty and Crafty+ share a protocol; the model is told apart by the
    # firmware major version after connecting (CRAFTY_BLE_SPEC.md §6).
    CRAFTY = "crafty"
    VENTY = "venty"
    VEAZY = "veazy"


# How each family is named in the device registry until it says otherwise.
FAMILY_MODEL_NAME: dict[DeviceFamily, str] = {
    DeviceFamily.VOLCANO_HYBRID: "Volcano Hybrid",
    DeviceFamily.CRAFTY: "Crafty",
    DeviceFamily.VENTY: "Venty",
    DeviceFamily.VEAZY: "Veazy",
}

# Portable devices: the app clamps the target to 40-210 °C for both families
# (CRAFTY_BLE_SPEC.md §3, VENTY_BLE_SPEC.md §5).
PORTABLE_MIN_TEMP = 0
PORTABLE_MAX_TEMP = 210
PORTABLE_MIN_DISPLAY_TEMP = 40
# The highest current temperature taken as a reading. 210 °C is only the top of
# the *target* range: boost and superboost add an offset on top of it, so a real
# reading can exceed it. Neither CRAFTY_BLE_SPEC.md nor VENTY_BLE_SPEC.md states
# a sentinel or "no reading" value; 230 °C (raw 2300) is the cut-off the
# janisstreib fork applies to both families, from its reading of the vendor web
# app — unverified on hardware.
PORTABLE_MAX_READING = 230


class VolcanoSensor(StrEnum):
    """Volcano sensor types."""

    VOLCANO = "volcano"
    FIRMWARE = "firmware"
    CURRENT_AUTO_OFF_TIME = "current_auto_off_time"
    CURRENT_ON_TIME = "current_on_time"
    HEAT_TIME = "heat_time"
    SHUT_OFF = "shut_off"
    LED_BRIGHTNESS = "led_brightness"
    AUTO_SHUTDOWN = "auto_shutdown"
    AT_TEMPERATURE = "at_temperature"
    HEATER_ACTIVE = "heater"
    PUMP_ACTIVE = "fan"
    ACTUATOR_FAULT = "actuator_fault"
    PRV1_ERROR = "prv1_error"
    SHOWING_CELSIUS = "showing_celsius"
    DISPLAY_ON_COOLING = "display_on_cooling"
    SERVICE_MODE = "service_mode"
    PRV2_ERROR = "prv2_error"
    VIBRATION = "vibration"
    RECONNECT = "reconnect"
    DELAYED_RECONNECT = "delayed_reconnect"
    AUTO_CONNECT = "auto_connect"
    CONNECTED = "connected"
    RSSI = "rssi"
    CONNECTED_ADDR = "connected_addr"
    MAINS_VOLTAGE = "mains_voltage"
    PRJ1 = "prj1"
    PRJ2 = "prj2"
    PRJ3 = "prj3"
    PRJ4 = "prj4"
    PRJ5 = "prj5"
    HIST1 = "hist1"
    HIST2 = "hist2"
    LAST_FAULT = "last_fault"
    BATTERY = "battery"
    BOOST_TEMP = "boost_temp"
    BOOST_MODE = "boost_mode"
    SUPERBOOST_MODE = "superboost_mode"
    AUTO_OFF_SECONDS = "auto_off_seconds"
    AUTO_OFF_COUNTDOWN = "auto_off_countdown"
    CHARGE_LED = "charge_led"
    FIND_DEVICE = "find_device"
    FIND_MODE = "find_mode"
    ERROR = "error"
    NEEDS_FACTORY_RESET = "needs_factory_reset"
    SYSTEM_STATUS = "system_status"
    BATTERY_STATUS1 = "battery_status1"
    BATTERY_STATUS2 = "battery_status2"
    SUPERBOOST_TEMP = "superboost_temp"
    HEATER_MODE = "heater_mode"
    CHARGING = "charging"
    BATTERY_CURRENT = "battery_current"
    BATTERY_VOLTAGE = "battery_voltage"
    BATTERY_HEALTH = "battery_health"
    CHARGE_CYCLES = "charge_cycles"
    DISCHARGE_CYCLES = "discharge_cycles"
    CHARGE_OPTIMIZATION = "charge_optimization"
    CHARGE_LIMIT = "charge_limit"
    BOOST_VISUALIZATION = "boost_visualization"
    BOOST_TIMEOUT_DISABLED = "boost_timeout_disabled"
    PERMANENT_BLUETOOTH = "permanent_bluetooth"
    PERMANENT_BLUETOOTH_ENABLED = "permanent_bluetooth_enabled"
    BRIGHTNESS = "brightness"
    CHARGING_TIME = "charging_time"
    COLOR = "color"
    BOOTLOADER_MODE = "bootloader_mode"
    TARGET_CHANGED_ON_DEVICE = "target_changed_on_device"


STORZ_BICKEL_MANUFACTURER_ID = 1736

# The Venty and Veazy advertise this one service (VENTY_BLE_SPEC.md §1).
QVAP_SERVICE_UUID = "00000000-5354-4f52-5a26-4249434b454c"
# The Crafty advertises its three services (CRAFTY_BLE_SPEC.md §1).
CRAFTY_SERVICE_UUIDS = (
    "00000001-4c45-4b43-4942-265a524f5453",
    "00000002-4c45-4b43-4942-265a524f5453",
    "00000003-4c45-4b43-4942-265a524f5453",
)
CRAFTY_NAME_PREFIXES = ("STORZ&BICKEL", "Storz&Bickel")


def detect_family(service_info: BluetoothServiceInfoBleak) -> DeviceFamily | None:
    """
    Decide which family an advertisement belongs to, or None.

    The order matters: the Volcano check is the one the integration has always
    made (name plus manufacturer id); the Venty/Veazy names are exact prefixes
    the vendor app matches on; a Qvap service with an unknown name is refused
    rather than guessed; the Crafty is last because its name is the least
    specific.
    """
    name = service_info.name or ""
    uuids = set(service_info.service_uuids)
    if (
        service_info.manufacturer_id == STORZ_BICKEL_MANUFACTURER_ID
        and "VOLCANO H" in name
    ):
        return DeviceFamily.VOLCANO_HYBRID
    if "S&B VY" in name:
        return DeviceFamily.VENTY
    if "S&B VZ" in name:
        return DeviceFamily.VEAZY
    if QVAP_SERVICE_UUID in uuids:
        return None
    if name.startswith(CRAFTY_NAME_PREFIXES) or uuids & set(CRAFTY_SERVICE_UUIDS):
        return DeviceFamily.CRAFTY
    return None


def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
    """Whether the advertisement belongs to a device this integration supports."""
    return detect_family(service_info) is not None
