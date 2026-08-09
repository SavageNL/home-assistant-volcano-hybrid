"""Constants for the VolcanoBLE."""

from enum import StrEnum

VOLCANO_HYBRID_MIN_TEMP = 0
VOLCANO_HYBRID_MAX_TEMP = 230

# The block temperature below which the device blanks its display again after
# the heater is switched off, used to decide when a cooldown has ended. The
# device does not report the state of its display, so this cannot be read back
# and is not measured here: it is what owners observe, and it lines up with the
# lowest temperature the device can be set to. Kept separate from that limit
# anyway, because they are two different facts that happen to share a value.
VOLCANO_HYBRID_DISPLAY_OFF_TEMP = 40


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
    PRV2_ERROR = "prv2_error"
    VIBRATION = "vibration"
    RECONNECT = "reconnect"
    DELAYED_RECONNECT = "delayed_reconnect"
    AUTO_CONNECT = "auto_connect"
    CONNECTED = "connected"
    RSSI = "rssi"
    CONNECTED_ADDR = "connected_addr"
    PRJ1 = "prj1"
    PRJ2 = "prj2"
    PRJ3 = "prj3"
    HIST1 = "hist1"
    HIST2 = "hist2"
