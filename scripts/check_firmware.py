"""
Compare the firmware version recorded in the integration against the vendor's.

Storz & Bickel's web app asks their server which firmware is current before it
offers an update. This script asks the same endpoint on a schedule so the
integration never has to, and reports when the answer stops matching
`LATEST_KNOWN_FIRMWARE` or when the endpoint itself changes shape.

Run by `.github/workflows/firmware-check.yml`. Uses only the standard library
so the workflow needs no dependency install. Exits non-zero when it has
something to report, and writes `status`, `title` and `body` to $GITHUB_OUTPUT.
"""

from __future__ import annotations

import ast
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Final

# The endpoint the vendor's app posts to; "version=true" asks only for the
# current version numbers. ("version=false" would return the firmware binary,
# which this check has no business downloading.)
ENDPOINT: Final = "https://app.storz-bickel.com/firmwareHybrid"
REQUEST_BODY: Final = {"version": "true"}
TIMEOUT_SECONDS: Final = 30
HTTP_OK: Final = 200
VALID: Final = 1
EXCERPT_CHARS: Final = 2000

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
FIRMWARE_MODULE: Final = (
    REPO_ROOT / "custom_components" / "volcano_hybrid" / "firmware.py"
)
CONSTANT_NAME: Final = "LATEST_KNOWN_FIRMWARE"

EXPECTED_SHAPE: Final = (
    "[{'valid': 1, 'majorApplication': int, 'minorApplication': int}]"
)


class CheckError(Exception):
    """A problem worth opening an issue about."""

    def __init__(self, status: str, title: str, body: str) -> None:
        """Record how the check failed."""
        super().__init__(title)
        self.status = status
        self.title = title
        self.body = body


def _excerpt(raw: str) -> str:
    """Quote a response body for an issue, bounded so it stays readable."""
    return f"```\n{raw[:EXCERPT_CHARS]}\n```"


def _schema_change(raw: str) -> CheckError:
    """Report that the endpoint no longer returns what this script expects."""
    body = (
        f"The response no longer looks like `{EXPECTED_SHAPE}`. The integration "
        "does not call this endpoint at runtime, so nothing is broken for "
        "users, but this check cannot tell whether new firmware shipped until "
        f"it is taught the new format.\n\nResponse was:\n\n{_excerpt(raw)}"
    )
    return CheckError("schema-change", "Volcano firmware endpoint changed shape", body)


def _endpoint_error(title: str, body: str) -> CheckError:
    """Report that the endpoint could not be reached or refused to answer."""
    return CheckError("endpoint-error", title, body)


def _format(version: tuple[int, int]) -> str:
    """Render a version the way Storz & Bickel write it."""
    return f"V{version[0]:02d}.{version[1]:02d}"


def read_recorded_version() -> tuple[int, int]:
    """
    Read LATEST_KNOWN_FIRMWARE out of the integration.

    Parsed rather than imported so this runs without Home Assistant installed.
    """
    tree = ast.parse(FIRMWARE_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            first = node.targets[0]
            target = first.id if isinstance(first, ast.Name) else None
        if target == CONSTANT_NAME and node.value is not None:
            major, minor = ast.literal_eval(node.value)
            return (int(major), int(minor))
    message = f"{CONSTANT_NAME} not found in {FIRMWARE_MODULE}"
    raise LookupError(message)


def fetch_published_version() -> tuple[int, int]:
    """Ask the vendor endpoint which firmware is current."""
    data = urllib.parse.urlencode(REQUEST_BODY).encode()
    request = urllib.request.Request(ENDPOINT, data=data, method="POST")
    try:
        # ENDPOINT is a fixed https literal, so the scheme cannot be attacker
        # controlled; S310 is about dynamic URLs.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            status = response.status
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        title = "Volcano firmware endpoint is unreachable"
        body = f"`POST {ENDPOINT}` failed: `{err}`."
        raise _endpoint_error(title, body) from err

    if status != HTTP_OK:
        title = "Volcano firmware endpoint returned an error"
        body = f"`POST {ENDPOINT}` responded with HTTP {status}."
        raise _endpoint_error(title, body)
    return _parse_response(raw)


def _decode(raw: str) -> dict[str, Any]:
    """Pull the single result object out of the response body."""
    try:
        payload = json.loads(raw)
        entry = payload[0]
    except (ValueError, TypeError, LookupError) as err:
        raise _schema_change(raw) from err
    if not isinstance(entry, dict):
        raise _schema_change(raw)
    return entry


def _parse_response(raw: str) -> tuple[int, int]:
    """Pull the version out of the endpoint's JSON, or report a shape change."""
    entry = _decode(raw)

    try:
        valid = int(entry["valid"])
    except (ValueError, TypeError, LookupError) as err:
        raise _schema_change(raw) from err
    if valid != VALID:
        title = "Volcano firmware endpoint reported an invalid response"
        body = f"The endpoint returned `valid != {VALID}`:\n\n{_excerpt(raw)}"
        raise _endpoint_error(title, body)

    try:
        return (int(entry["majorApplication"]), int(entry["minorApplication"]))
    except (ValueError, TypeError, LookupError) as err:
        raise _schema_change(raw) from err


def build_outdated_report(
    recorded: tuple[int, int], published: tuple[int, int]
) -> CheckError:
    """Describe a version mismatch and what to do about it."""
    direction = "newer than" if published > recorded else "different from"
    body = (
        f"Storz & Bickel now publish **{_format(published)}** for the Volcano "
        f"Hybrid, which is {direction} the **{_format(recorded)}** recorded in "
        "`custom_components/volcano_hybrid/firmware.py`.\n\n"
        "Users are not affected until this is acted on: the integration reports "
        f"devices as up to date at {_format(recorded)} and never contacts this "
        "endpoint itself.\n\n"
        "To close this out:\n\n"
        "1. Flash the new firmware with the official web app "
        "(<https://app.storz-bickel.com/>).\n"
        "2. Check the integration still reads and controls the vaporizer — in "
        "particular the status registers, since new firmware can move bits.\n"
        f"3. Bump `{CONSTANT_NAME}` to `{published}` and note the supported "
        "firmware in `CHANGELOG.md`.\n"
    )
    return CheckError(
        "outdated",
        f"Volcano Hybrid firmware {_format(published)} is available",
        body,
    )


def write_outputs(status: str, title: str, body: str) -> None:
    """Publish the result to the workflow, when running inside one."""
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8") as handle:
        handle.write(f"status={status}\n")
        handle.write(f"title={title}\n")
        handle.write(f"body<<FIRMWARE_CHECK_EOF\n{body}\nFIRMWARE_CHECK_EOF\n")


def main() -> int:
    """Run the check and report the outcome."""
    recorded = read_recorded_version()
    try:
        published = fetch_published_version()
        if published != recorded:
            raise build_outdated_report(recorded, published)
    except CheckError as failure:
        print(f"::warning::{failure.title}")
        print(failure.body)
        write_outputs(failure.status, failure.title, failure.body)
        return 1

    print(f"Recorded firmware {_format(recorded)} still matches the vendor endpoint.")
    write_outputs("ok", "", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
