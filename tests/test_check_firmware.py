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
from unittest.mock import MagicMock, patch

import pytest

from custom_components.volcano_hybrid.firmware import LATEST_KNOWN_FIRMWARE

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
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

_RECORDED = LATEST_KNOWN_FIRMWARE["volcano_hybrid"]
assert _RECORDED is not None
LATEST: tuple[int, int] = _RECORDED


def _response(
    family: str = "volcano_hybrid",
    version: tuple[int, int] = LATEST,
    **overrides: Any,
) -> str:
    """Build a response body shaped like a family's vendor endpoint."""
    payload: dict[str, Any] = {
        "valid": 1,
        "majorApplication": version[0],
        "minorApplication": version[1],
    }
    if family != "volcano_hybrid":
        payload |= {"majorBootloader": 1, "minorBootloader": 0}
    payload.update(overrides)
    return json.dumps([payload])


def test_reads_the_versions_recorded_in_the_integration() -> None:
    """The constant is read from source without importing Home Assistant."""
    assert check_firmware.read_recorded_versions() == LATEST_KNOWN_FIRMWARE


def test_every_recorded_family_has_an_endpoint() -> None:
    """A family added to the constant cannot be silently left unchecked."""
    assert set(check_firmware.ENDPOINTS) == set(LATEST_KNOWN_FIRMWARE)


@pytest.mark.parametrize("family", ["volcano_hybrid", "venty", "veazy"])
def test_parses_a_healthy_response(family: str) -> None:
    """A well-formed response yields the published version."""
    raw = _response(family, (1, 9))
    assert check_firmware._parse_response(raw, family) == (1, 9)  # noqa: SLF001


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
    published = (LATEST[0], LATEST[1] + 1)
    failure = check_firmware.build_outdated_report("volcano_hybrid", LATEST, published)

    assert failure.status == "outdated"
    assert "Volcano Hybrid" in failure.title
    assert check_firmware._format(published) in failure.title  # noqa: SLF001
    assert check_firmware._format(published) in failure.body  # noqa: SLF001
    assert check_firmware._format(LATEST) in failure.body  # noqa: SLF001
    assert "LATEST_KNOWN_FIRMWARE" in failure.body


def test_family_without_a_recorded_version_is_informational(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    A family nobody has verified firmware for yet only prints what is published.

    Reporting it would keep an issue open (and the weekly run red) for as long
    as nobody owns the device, which says nothing about a firmware release.
    """
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        check_firmware,
        "read_recorded_versions",
        lambda: {"volcano_hybrid": LATEST, "venty": None, "veazy": None},
    )
    monkeypatch.setattr(
        check_firmware,
        "fetch_published_version",
        _fake_fetch({"volcano_hybrid": LATEST, "venty": (1, 9), "veazy": (1, 7)}),
    )

    assert check_firmware.main() == 0
    assert "status=ok\n" in output.read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    assert "venty: published V01.09; no version recorded yet" in printed
    assert "veazy: published V01.07; no version recorded yet" in printed
    assert "::warning::" not in printed


def _fake_fetch(
    responses: Mapping[str, tuple[int, int] | Exception],
) -> Callable[[str], tuple[int, int]]:
    """Stand in for the network: answer per family, never touch a socket."""

    def fetch(family: str) -> tuple[int, int]:
        result = responses[family]
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


def test_main_is_quiet_when_every_family_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded versions equal to the published ones report ok."""
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    versions = {"volcano_hybrid": LATEST, "venty": (1, 9), "veazy": (1, 9)}
    monkeypatch.setattr(check_firmware, "read_recorded_versions", lambda: versions)
    monkeypatch.setattr(
        check_firmware, "fetch_published_version", _fake_fetch(versions)
    )

    assert check_firmware.main() == 0
    assert "status=ok\n" in output.read_text(encoding="utf-8")


def test_main_reports_every_failing_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    One family's standing problem must not hide another family's.

    A family without a recorded version is still checked for endpoint errors
    and shape changes: those mean the check itself has stopped working.
    """
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        check_firmware,
        "read_recorded_versions",
        lambda: {"volcano_hybrid": LATEST, "venty": None, "veazy": None},
    )
    monkeypatch.setattr(
        check_firmware,
        "fetch_published_version",
        _fake_fetch(
            {
                "volcano_hybrid": (LATEST[0], LATEST[1] + 1),
                "venty": check_firmware._schema_change("[]", "venty"),  # noqa: SLF001
                "veazy": check_firmware._endpoint_error("down", "body"),  # noqa: SLF001
            }
        ),
    )

    assert check_firmware.main() == 1
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("failures=")
    entries = json.loads(lines[0].removeprefix("failures="))
    assert [entry["status"] for entry in entries] == [
        "volcano_hybrid-outdated",
        "venty-schema-change",
        "veazy-endpoint-error",
    ]
    assert entries[2]["title"] == "down"
    assert entries[2]["body"] == "body"


def test_rejects_a_response_that_is_not_text() -> None:
    """Undecodable bytes are a reported schema change, not a crash."""
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"\xff\xfe\x00"
    response.__enter__.return_value = response
    with (
        patch.object(check_firmware.urllib.request, "urlopen", return_value=response),
        pytest.raises(check_firmware.CheckError) as err,
    ):
        check_firmware.fetch_published_version("venty")
    assert err.value.status == "schema-change"
    assert "Venty" in err.value.title


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


def test_excerpt_fence_cannot_be_closed_by_the_response() -> None:
    """A response quoting ``` stays inside the code block in the issue body."""
    raw = "x\n```\n[click](https://example.invalid) @someone\n````\ny"
    excerpt = check_firmware._excerpt(raw)  # noqa: SLF001
    fence = excerpt.split("\n", 1)[0]
    assert fence == "`" * 5
    assert excerpt == f"{fence}\n{raw}\n{fence}"


def test_untrusted_output_is_printed_with_workflow_commands_off(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Workflow commands quoted from a response are not acted on by the runner."""
    check_firmware._print_untrusted("::add-mask::secret\nbody")  # noqa: SLF001
    lines = capsys.readouterr().out.splitlines()
    token = lines[0].removeprefix("::stop-commands::")
    assert lines[0] != token
    assert len(token) == 32
    assert lines[1:] == ["::add-mask::secret", "body", f"::{token}::"]
