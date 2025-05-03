"""Constants for the VolcanoBLE."""

from enum import StrEnum


class VolcanoSensor(StrEnum):
    """Volcano sensor types."""

    VOLCANO = "volcano"
    CURRENT_AUTO_OFF_TIME = "current_auto_off_time"
    CURRENT_ON_TIME = "current_on_time"
    HEAT_TIME = "heat_time"
    SHUT_OFF = "shut_off"
    LED_BRIGHTNESS = "led_brightness"
    AUTO_SHUTDOWN = "auto_shutdown"
    PRV1_ERROR = "prv1_error"
    SHOWING_CELSIUS = "showing_celsius"
    DISPLAY_ON_COOLING = "display_on_cooling"
    PRV2_ERROR = "prv2_error"
    VIBRATION = "vibration"
    RECONNECT = "reconnect"
    CONNECTED = "connected"
    RSSI = "rssi"
