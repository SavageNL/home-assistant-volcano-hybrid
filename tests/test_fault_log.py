"""Tests for decoding the fault log the device serves as HIST1/HIST2."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble.fault_log import (
    FAULT_CODES,
    FAULT_OPTIONS,
    FAULT_UNKNOWN,
    decode_fault_log,
)

# What a V01.03 device answered, verbatim (VOLCANO_BLE_SPEC.md §3.5).
HIST1_READ_FROM_A_DEVICE = "6161616161617261"
HIST2_READ_FROM_A_DEVICE = "0000000000000000"


def test_decodes_the_values_read_from_a_device() -> None:
    """The fields are two-digit decimal codes, not the bytes of hex text."""
    timing = {"code": "61", "fault": "heater_timing_bit4"}
    assert decode_fault_log(HIST1_READ_FROM_A_DEVICE) == [
        timing,
        timing,
        timing,
        timing,
        timing,
        timing,
        {"code": "72", "fault": "heater_feedback_deviation"},
        timing,
    ]
    # Every slot empty is an empty log, not eight faults with code 0.
    assert decode_fault_log(HIST2_READ_FROM_A_DEVICE) == []


def test_every_documented_code_decodes_to_an_option() -> None:
    """Each code in the table is a state the sensor is allowed to report."""
    for code, fault in FAULT_CODES.items():
        assert decode_fault_log(f"{code:02d}") == [
            {"code": f"{code:02d}", "fault": fault}
        ]
        assert fault in FAULT_OPTIONS


def test_empty_slots_are_dropped_between_entries() -> None:
    """A partly filled log reports only the slots that hold a code."""
    assert decode_fault_log("00530000") == [{"code": "53", "fault": "sensor_short"}]


def test_an_unknown_code_keeps_its_field() -> None:
    """A code no table entry covers stays reportable, and stays legible."""
    assert decode_fault_log("9953") == [
        {"code": "99", "fault": FAULT_UNKNOWN},
        {"code": "53", "fault": "sensor_short"},
    ]
    assert FAULT_UNKNOWN in FAULT_OPTIONS


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, []),
        ("", []),
        # An odd length: the complete fields decode, the half field is dropped
        # rather than guessed at.
        ("536", [{"code": "53", "fault": "sensor_short"}]),
        ("5", []),
        # Not decimal at all — what _decode_ascii falls back to when the device
        # answers something that is not text, and what a hexing client would
        # have written into an issue.
        (
            "aaaaaara",
            [
                {"code": "aa", "fault": FAULT_UNKNOWN},
                {"code": "aa", "fault": FAULT_UNKNOWN},
                {"code": "aa", "fault": FAULT_UNKNOWN},
                {"code": "ra", "fault": FAULT_UNKNOWN},
            ],
        ),
        ("  ", [{"code": "  ", "fault": FAULT_UNKNOWN}]),
    ],
)
def test_malformed_input_never_raises(
    text: str | None, expected: list[dict[str, str]]
) -> None:
    """The decode runs on whatever the device sent, inside a read callback."""
    assert decode_fault_log(text) == expected
