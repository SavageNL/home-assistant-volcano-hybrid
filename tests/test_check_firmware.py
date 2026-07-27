"""
Tests for the scheduled firmware endpoint check.

The check is the only thing that notices new firmware, so its failure paths
matter: a silently broken check looks exactly like "no new firmware".
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from custom_components.volcano_hybrid.firmware import LATEST_KNOWN_FIRMWARE

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_firmware.py"


def _load() -> ModuleType:
    """Import the script by path; scripts/ is deliberately not a package."""
    spec = importlib.util.spec_from_file_location("check_firmware", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_firmware = _load()


def _response(**overrides: Any) -> str:
    """Build a response body shaped like the vendor endpoint's."""
    payload = {
        "valid": 1,
        "majorApplication": LATEST_KNOWN_FIRMWARE[0],
        "minorApplication": LATEST_KNOWN_FIRMWARE[1],
    }
    payload.update(overrides)
    return json.dumps([payload])


def test_reads_the_version_recorded_in_the_integration() -> None:
    """The constant is read from source without importing Home Assistant."""
    assert check_firmware.read_recorded_version() == LATEST_KNOWN_FIRMWARE


def test_parses_a_healthy_response() -> None:
    """A well-formed response yields the published version."""
    assert check_firmware._parse_response(_response()) == LATEST_KNOWN_FIRMWARE  # noqa: SLF001


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "{}",
        "[]",
        '[{"valid": 1}]',
        '[{"valid": 1, "majorApplication": "one", "minorApplication": 3}]',
        '[{"valid": 1, "applicationVersion": "1.3"}]',
    ],
)
def test_reports_a_schema_change(raw: str) -> None:
    """Anything that is not the expected shape is flagged, not guessed at."""
    with pytest.raises(check_firmware.CheckError) as err:
        check_firmware._parse_response(raw)  # noqa: SLF001
    assert err.value.status == "schema-change"


def test_reports_an_invalid_response() -> None:
    """The endpoint's own "not valid" answer is a failure, not a version."""
    with pytest.raises(check_firmware.CheckError) as err:
        check_firmware._parse_response(_response(valid=0))  # noqa: SLF001
    assert err.value.status == "endpoint-error"


def test_outdated_report_names_both_versions() -> None:
    """The issue body says what shipped, what is recorded, and what to do."""
    published = (LATEST_KNOWN_FIRMWARE[0], LATEST_KNOWN_FIRMWARE[1] + 1)
    failure = check_firmware.build_outdated_report(LATEST_KNOWN_FIRMWARE, published)

    assert failure.status == "outdated"
    assert check_firmware._format(published) in failure.title  # noqa: SLF001
    assert check_firmware._format(published) in failure.body  # noqa: SLF001
    assert check_firmware._format(LATEST_KNOWN_FIRMWARE) in failure.body  # noqa: SLF001
    assert "LATEST_KNOWN_FIRMWARE" in failure.body


def test_writes_workflow_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The workflow reads status/title/body back out of $GITHUB_OUTPUT."""
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    check_firmware.write_outputs("outdated", "A title", "line one\nline two")

    written = output.read_text(encoding="utf-8")
    assert "status=outdated\n" in written
    assert "title=A title\n" in written
    # A multi-line body has to use the delimiter form or the workflow breaks.
    assert (
        "body<<FIRMWARE_CHECK_EOF\nline one\nline two\nFIRMWARE_CHECK_EOF\n" in written
    )


def test_writing_outputs_is_a_no_op_outside_a_workflow() -> None:
    """Running the script by hand should not need GITHUB_OUTPUT set."""
    check_firmware.write_outputs("ok", "", "")
