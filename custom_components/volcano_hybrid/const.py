"""Constants for the Volcano Hybrid integration."""

from .volcano_ble.const import (
    VOLCANO_HYBRID_MAX_TEMP,
    VOLCANO_HYBRID_MIN_TEMP,
)

DOMAIN = "volcano_hybrid"

VOLCANO_HYBRID_MIN_DISPLAY_TEMP = 40

__all__ = [
    "DOMAIN",
    "VOLCANO_HYBRID_MAX_TEMP",
    "VOLCANO_HYBRID_MIN_DISPLAY_TEMP",
    "VOLCANO_HYBRID_MIN_TEMP",
]
