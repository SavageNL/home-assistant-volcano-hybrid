"""
Firmware version tracking for the Volcano Hybrid.

The vaporizer cannot report whether a newer firmware exists; only Storz &
Bickel's web app knows that, by asking their server. Rather than make every
installation call out to that server, the newest firmware known at release
time is recorded here and compared against what the device reports.

`.github/workflows/firmware-check.yml` polls the vendor endpoint on a schedule
and opens an issue when it disagrees with `LATEST_KNOWN_FIRMWARE`, which is the
signal to test the new firmware and bump the constant below. That keeps the
integration itself free of any network dependency.
"""

from __future__ import annotations

import re
from typing import Final

# The newest firmware Storz & Bickel published for the Volcano Hybrid as of the
# last release of this integration, as (major, minor).
#
# Do not bump this by hand without flashing the firmware and confirming the
# integration still works against it: the whole point of the constant is that
# it only ever names a version somebody actually verified.
LATEST_KNOWN_FIRMWARE: Final[tuple[int, int]] = (1, 3)

# Where a user installs it today. Flashing is a BLE bootloader protocol, not
# something only a browser can drive, so this could be implemented here; see
# "Why there is no install" in CLAUDE.md for why it is not.
FIRMWARE_UPDATE_URL: Final = "https://app.storz-bickel.com/"

# The device reports a dotted version with a letter prefix, e.g. "V01.03.00.00".
# Only the first two components identify the firmware release.
_VERSION_NUMBERS = re.compile(r"\d+")


def parse_firmware_version(raw: str | None) -> tuple[int, int] | None:
    """
    Extract (major, minor) from a version string the device reported.

    Returns None when the string is missing or carries no recognisable version,
    so callers report an unknown version rather than inventing one.
    """
    if raw is None:
        return None
    numbers = _VERSION_NUMBERS.findall(raw)
    minimum_components = 2
    if len(numbers) < minimum_components:
        return None
    return (int(numbers[0]), int(numbers[1]))


def format_firmware_version(version: tuple[int, int]) -> str:
    """Render a version the way Storz & Bickel write it, e.g. "V01.03"."""
    major, minor = version
    return f"V{major:02d}.{minor:02d}"


def latest_firmware_version(
    installed: tuple[int, int] | None,
) -> tuple[int, int] | None:
    """
    Return the newest firmware known for a device on `installed`.

    A device can legitimately run something newer than this integration knows
    about, if it was flashed after the last release. Reporting the recorded
    constant regardless would tell that user to "update" to older firmware, so
    whatever is already installed wins when it is ahead.
    """
    if installed is None:
        return None
    return max(installed, LATEST_KNOWN_FIRMWARE)
