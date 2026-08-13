"""Decoding of the fault log the device serves as HIST1 / HIST2."""

from __future__ import annotations

# The controller's fault codes, keyed by the *decimal* value it writes into the
# log. VOLCANO_BLE_SPEC.md §3.2.1 lists each code as hex with the decimal in
# brackets; the log spells the decimal, so that is what this table is keyed by,
# with the hex kept alongside to make the two readable against each other. The
# values are translation keys, so no English is decided here — the names live
# in strings.json, where they can be translated.
FAULT_CODES: dict[int, str] = {
    45: "regulation_pinned_low",  # 0x2D
    53: "sensor_short",  # 0x35
    54: "sensor_open",  # 0x36
    60: "heater_timing_bit3",  # 0x3C
    61: "heater_timing_bit4",  # 0x3D
    63: "regulation_average_high",  # 0x3F
    64: "regulation_out_of_range",  # 0x40
    65: "comms_timeout",  # 0x41
    67: "heater_feedback_low",  # 0x43
    68: "heater_feedback_high",  # 0x44
    72: "heater_feedback_deviation",  # 0x48
}

# Reported when the log holds no entry at all.
FAULT_NONE = "none"
# Reported for a field the table above does not know. Deliberately not called
# `unknown`: Home Assistant already uses that state for "this entity has no
# value", so an enum sensor answering it would be indistinguishable from one
# that has not read the device yet. The field is kept verbatim in the decoded
# entry, so an unrecognised code still reaches a bug report as itself.
FAULT_UNKNOWN = "unknown_code"

# Every state the fault sensor may report. A Home Assistant enum sensor whose
# state is not one of its options is invalid, which is why an unrecognised code
# has to map onto one of these rather than be reported as itself.
FAULT_OPTIONS: list[str] = [FAULT_NONE, *FAULT_CODES.values(), FAULT_UNKNOWN]

# The log is text divided into fixed-width fields; an unused slot reads as zero.
FAULT_FIELD_WIDTH = 2
_EMPTY_SLOT = "00"


def decode_fault_log(text: str | None) -> list[dict[str, str]]:
    """
    Decode one fault-log characteristic into the entries it holds.

    The device answers with 16 ASCII characters, and those characters are not
    hex bytes: they are eight two-character **decimal** fields, each one a
    fault code from VOLCANO_BLE_SPEC.md §3.2.1. The device read for the spec
    answered `6161616161617261`, which is seven logged `0x3D` (61) and one
    `0x48` (72); read as hex bytes the same characters would be `0x61` and
    `0x72`, which are not codes at all. Unused slots read `00` and are dropped
    here — the raw text is reported next to this, so nothing is hidden.

    Entries are returned in the order the device wrote them. The spec describes
    the ring as most recent first, which is its reading of the firmware and has
    not been confirmed against a device, so nothing is reordered here.

    Nothing in here raises. It decodes whatever the device sent, from inside a
    read callback where an exception would take the whole connect down: text of
    an odd length, or with fields that are not numbers, yields the entries it
    can and reports the rest as unrecognised rather than failing.
    """
    if not text:
        return []

    # A trailing half field is dropped rather than guessed at.
    fields = (
        text[start : start + FAULT_FIELD_WIDTH]
        for start in range(0, len(text) - FAULT_FIELD_WIDTH + 1, FAULT_FIELD_WIDTH)
    )
    return [
        {"code": field, "fault": _fault_for_field(field)}
        for field in fields
        if field != _EMPTY_SLOT
    ]


def _fault_for_field(field: str) -> str:
    """Return the option key one log field stands for, whatever it holds."""
    try:
        code = int(field)
    except ValueError:
        return FAULT_UNKNOWN
    return FAULT_CODES.get(code, FAULT_UNKNOWN)
