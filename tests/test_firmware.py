"""Tests for the firmware version helpers."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.firmware import (
    LATEST_KNOWN_FIRMWARE,
    format_firmware_version,
    latest_firmware_version,
    parse_firmware_version,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # What the vaporizer actually reports.
        ("V01.03.00.00", (1, 3)),
        ("V01.02.00.00", (1, 2)),
        # Tolerated variations, so a firmware that shortens or reformats the
        # string does not silently turn into "unknown".
        ("V01.03", (1, 3)),
        ("1.3", (1, 3)),
        ("V10.11.00.00", (10, 11)),
        # Nothing usable.
        (None, None),
        ("", None),
        ("V01", None),
        ("unknown", None),
    ],
)
def test_parse_firmware_version(
    raw: str | None, expected: tuple[int, int] | None
) -> None:
    """Version strings are reduced to their major and minor components."""
    assert parse_firmware_version(raw) == expected


def test_format_firmware_version() -> None:
    """Versions are rendered the way Storz & Bickel write them."""
    assert format_firmware_version((1, 3)) == "V01.03"
    assert format_firmware_version((10, 11)) == "V10.11"


def test_latest_is_the_recorded_version_when_the_device_is_behind() -> None:
    """A device on older firmware is told about the version we know of."""
    older = (LATEST_KNOWN_FIRMWARE[0], LATEST_KNOWN_FIRMWARE[1] - 1)
    assert latest_firmware_version(older) == LATEST_KNOWN_FIRMWARE


def test_latest_matches_a_device_that_is_current() -> None:
    """A device on the recorded version reports no update."""
    assert latest_firmware_version(LATEST_KNOWN_FIRMWARE) == LATEST_KNOWN_FIRMWARE


def test_latest_never_points_backwards() -> None:
    """
    A device flashed past what this release knows about is left alone.

    Reporting the recorded constant here would tell the user to "update" to
    firmware older than the one they are running.
    """
    newer = (LATEST_KNOWN_FIRMWARE[0], LATEST_KNOWN_FIRMWARE[1] + 1)
    assert latest_firmware_version(newer) == newer

    much_newer = (LATEST_KNOWN_FIRMWARE[0] + 1, 0)
    assert latest_firmware_version(much_newer) == much_newer


def test_latest_is_unknown_without_a_device_version() -> None:
    """Nothing is claimed before the vaporizer has reported its firmware."""
    assert latest_firmware_version(None) is None
