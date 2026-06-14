"""Constants for the Volcano Hybrid integration."""

from .volcano_ble.const import (
    VOLCANO_HYBRID_MAX_TEMP,
    VOLCANO_HYBRID_MIN_TEMP,
)

DOMAIN = "volcano_hybrid"

VOLCANO_HYBRID_MIN_DISPLAY_TEMP = 40

# Options
CONF_AUTO_CONNECT_DELAY = "auto_connect_delay"
CONF_DELAYED_RECONNECT_DELAY = "delayed_reconnect_delay"

# A short wait before auto-connecting, so a freshly seen advertisement reaches
# every Bluetooth proxy and the best path is chosen instead of the first one.
DEFAULT_AUTO_CONNECT_DELAY = 1.0
# The delayed reconnect button stays disconnected this long, long enough to
# guarantee a fresh advertisement (the device advertises ~every 10s when idle).
DEFAULT_DELAYED_RECONNECT_DELAY = 11.0

__all__ = [
    "CONF_AUTO_CONNECT_DELAY",
    "CONF_DELAYED_RECONNECT_DELAY",
    "DEFAULT_AUTO_CONNECT_DELAY",
    "DEFAULT_DELAYED_RECONNECT_DELAY",
    "DOMAIN",
    "VOLCANO_HYBRID_MAX_TEMP",
    "VOLCANO_HYBRID_MIN_DISPLAY_TEMP",
    "VOLCANO_HYBRID_MIN_TEMP",
]
