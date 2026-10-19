# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A HACS custom integration for Home Assistant that controls Storz & Bickel vaporizers over Bluetooth LE: the Volcano Hybrid, Crafty / Crafty+, Venty and Veazy (the latter three are untested on hardware). It targets the platinum tier of Home Assistant's integration quality scale and `custom_components/volcano_hybrid/quality_scale.yaml` tracks the status of every rule, but it deliberately does not declare `quality_scale` in the manifest: the tier is awarded by the HA core team to core integrations, so a custom integration stating one would be claiming a rating nobody granted. Treat the scale as the standard to hold the code to — changes should not regress any rule (strict typing, full config-flow test coverage, `PARALLEL_UPDATES` in every platform, translated exceptions, etc.).

## Commands

Tests and mypy only run on Linux (`homeassistant.runner` imports `fcntl`). On Windows, use an ephemeral container (docker CLI maps to podman on some machines):

```
podman run --rm -v "<repo>:/workspace" -w /workspace python:3.14 sh -c "pip install -q -r requirements.txt && python -m pytest tests -q && mypy --config-file mypy.ini"
```

On Linux (CI uses ubuntu-latest, the devcontainer works too):

- `scripts/test` — pytest (`scripts/test tests/test_climate.py -k name` for a single test)
- `scripts/lint` — ruff format + ruff check --fix + strict mypy
- `pytest tests --cov=custom_components.volcano_hybrid` — coverage (Silver requires ≥95%; config_flow.py must be 100%)

Caveat: when the repo is bind-mounted from NTFS into a Linux container, every file looks executable and ruff reports false `EXE002` errors. Git records mode 100644, so CI is unaffected; to check ruff locally, run it against a clean `git clone` inside the container.

Ruff runs with `select = ["ALL"]` and mypy mirrors the strict settings HA core applies to platinum integrations — both configs are based on HA core's and the comments in `.ruff.toml` explain each ignore.

## Dependency pinning rules

`requirements.txt` is dev/test only (the manifest declares the runtime requirements). Two pins are constrained:

- `homeassistant` is locked to whatever `pytest-homeassistant-custom-component` (latest) pins — upgrading HA past it makes pip resolution fail.
- The bluetooth libs (`habluetooth`, `bleak`, `bleak-retry-connector`) mirror what HA's bluetooth component ships; see `homeassistant/components/bluetooth/manifest.json` for the target HA version.

Releases are tag-driven: push a git tag (e.g. `git tag 1.0.4 && git push origin 1.0.4`) and `release.yml` does the rest — it stamps the tag's version into `manifest.json` in CI (never committed), zips the integration into `volcano_hybrid.zip`, and publishes a GitHub release with that asset. HACS installs from the zip (`zip_release`/`filename` in `hacs.json`), so the committed `manifest.json` version is just a placeholder overwritten at build time. Tags containing `-alpha`/`-beta`/`-rc` are auto-marked as pre-releases. Git prevents reusing a tag, so no manual version bookkeeping is needed.

The release notes come from `CHANGELOG.md`: the workflow copies the `## [Unreleased]` section of the tagged commit into the release body, with GitHub's generated commit list appended. There is no version heading to pre-set — user-facing changes just need an `## [Unreleased]` entry as they land, and tagging remains the only release step. An empty section only warns (the tag already points at the commit, so it cannot be repaired after the fact). Renaming the block to the shipped version afterwards is optional bookkeeping that nothing depends on.

## Firmware version tracking

The vaporizers cannot report whether newer firmware exists — only Storz & Bickel's server knows, and the official web app asks it (for the Volcano Hybrid: `POST https://app.storz-bickel.com/firmwareHybrid`, body `version=true`, returning `[{"valid":1,"majorApplication":1,"minorApplication":3}]`; the Venty and Veazy have their own request against `https://app.storz-bickel.com/firmware`, see `ENDPOINTS` in `scripts/check_firmware.py`). The integration deliberately does **not** call these endpoints: it would put a cloud dependency behind a `local_push` integration that otherwise works entirely offline. The Crafty has no firmware tracking and no `update` entity.

Instead `LATEST_KNOWN_FIRMWARE` in `custom_components/volcano_hybrid/firmware.py` records, **per family**, the newest firmware someone actually flashed and tested, and the `update` entity compares the device against its family's entry. The Volcano Hybrid has one; the Venty and Veazy are `None` until somebody verifies a firmware, which means the entity shows no "latest" at all rather than echoing the installed version. `.github/workflows/firmware-check.yml` runs `scripts/check_firmware.py` weekly to poll every family's endpoint and opens an issue for each family whose published version moves past its constant, whose endpoint fails, or whose JSON changes shape. A family recorded as `None` is informational: the run prints its published version and raises nothing for it, though its endpoint failing or changing shape is still reported. Issues are labelled `firmware-watch` plus `firmware-watch:<family>-<status>` (for example `volcano_hybrid-outdated`, `venty-endpoint-error`, `veazy-schema-change`) and deduplicated on **both**, so at most one issue per family and kind of problem is open at a time, a stale endpoint failure cannot mask a firmware release, and one family's standing problem cannot hide another's. While one is open the weekly run only goes red; closing it without addressing the cause lets the next run raise it again.

So the constants are only ever bumped by hand, after verifying the integration against the new firmware — that is the point of them. `latest_firmware_version` never reports a version older than what the device is running, so a user who flashed ahead of a release is not told to downgrade.

### Why there is no install

Not because it is impossible. "Web Bluetooth" is only the browser's API for the same GATT the integration already speaks; the flashing path is ordinary BLE and bleak could drive all of it. `VOLCANO_BLE_SPEC.md` §6 documents the whole bootloader protocol — the unlock write, the telegram framing and command set, and the page/CRC sequence.

The reasons not to do it are risk and licensing, and they should be argued on those terms rather than by pretending it cannot be done:

- A flash interrupted partway is the worst failure this integration could cause. The vendor app holds one direct browser connection and tells the user to keep the device powered; Home Assistant may be going through an ESPHome Bluetooth proxy with its own reconnect and retry behaviour, which is a much less controlled link for a multi-minute write. Bootloader mode is at least detectable and resumable (the bootloader version string contains `BL`), so a failed flash is recoverable rather than terminal — but recovery still means a browser.
- The firmware binary is Storz & Bickel's, served from their endpoint. Downloading and pushing it from third-party software is a licensing question, not just a technical one.

If it is ever built, it belongs behind an explicit opt-in, should refuse to start over a proxied connection, and needs the CRC and page sequence verified against a device that can be recovered. The Venty and Veazy protocol layer goes the other way on purpose: `QvapDevice` refuses the forbidden commands (`0x0C`, `0x30`) outright and, until the device confirms it is not in its bootloader, everything but the firmware query.

## Examples site

Usage examples do not live in the README (it has one link to them) but on a GitHub Pages site built with MkDocs Material: `mkdocs.yml` at the root, the pages in `docs/`, the build pinned in `requirements-docs.txt`. `.github/workflows/docs.yml` runs `mkdocs build --strict` on every change to them and deploys from `main`; Pages must be set to deploy from GitHub Actions in the repository settings. Build locally with `pip install -r requirements-docs.txt && mkdocs serve`.

Scripts and automations with settings ship as blueprints in `blueprints/<script|automation>/volcano_hybrid/`, and their page offers both an import button (a `my.home-assistant.io` blueprint-import link to the file on `main`) and a standalone YAML version, so a logic change has to land in both. `tests/test_blueprints.py` expands every blueprint through Home Assistant's own blueprint and script/automation validation, checks each `source_url` points at the file itself, and fails when a blueprint has no import button in `docs/`.

## Architecture

Three protocol references live in the repo root, one per protocol:

- `VOLCANO_BLE_SPEC.md` — the Volcano Hybrid: every service and characteristic, value encodings, the PRJSTAT1/2/3 bit maps (including which bits are still undecoded and how to settle them), and the firmware-update protocol.
- `CRAFTY_BLE_SPEC.md` — the Crafty and Crafty+, decoded from the vendor web app.
- `VENTY_BLE_SPEC.md` — the Qvap protocol spoken by the Venty and Veazy (framed commands, polled rather than pushed).

Keep them in sync when the protocol layer learns something new about a device, and cite their confidence tags — CONFIRMED / STRONG / SPECULATIVE — rather than promoting a guess. `tests/test_spec_traceability.py` fails when a UUID or mask in `crafty.py`, `crafty_data.py`, `qvap.py` or `qvap_frames.py` is missing from the spec it implements. Only CONFIRMED / STRONG features are exposed as entities. The Crafty, Venty and Veazy are untested on hardware; say so in the README and CHANGELOG until that changes.

Two layers, deliberately separated:

- `custom_components/volcano_hybrid/volcano_ble/` — protocol layer, no Home Assistant imports (only bleak/habluetooth):
  - `const.py` — `DeviceFamily`, `detect_family()`, the `VolcanoSensor` key enum, limits.
  - `data.py` — `TrackedValue` and the `DeviceData` base (the single state object shared with the HA layer, including its `capabilities`); `volcano_hybrid_data.py`, `crafty_data.py` and `qvap_data.py` hold the per-family subclasses (`VolcanoHybridData`, `CraftyData`, `QvapData` for both Venty and Veazy).
  - `device.py` — `StorzBickelDevice`, the base class that owns the GATT connection, connect lock, RSSI/connected-address tracking and the `async_manual_update()` template, plus `UnsupportedCommandError`.
  - `volcano_ble.py` (`VolcanoDevice`, alias `VolcanoBLE`), `crafty.py` (`CraftyDevice`), `qvap.py` (`QvapDevice` with `VentyDevice` / `VeazyDevice`) — one device class per protocol; `qvap_frames.py` is the pure build/parse layer for Qvap frames.
  - `families.py` — the registry mapping each `DeviceFamily` to its device and data class, and `create_device()`.
- `custom_components/volcano_hybrid/` — HA layer. `VolcanoHybridCoordinator` (in `coordinator.py`) wraps whichever device `create_device()` returns for the entry's family; entities are thin `CoordinatorEntity` subclasses of `VolcanoHybridEntity` (`entity.py`), which derives unique IDs as `{address}-{description.key}` and supports an `always_available` flag for diagnostic entities (RSSI, connected) that must outlive the connection. The config entry stores `{address, model}` (config flow `VERSION = 1`, `MINOR_VERSION = 2`; entries at minor version 1 are migrated to `volcano_hybrid`, and the bump is a minor one so that 1.0.5 still loads them after a rollback — Home Assistant refuses an entry whose major version is above its handler's).

### Capability filtering

Each platform keeps one description table covering every family and creates only the rows whose key is in `coordinator.data.capabilities`; that set is declared by the data class. A key that no family lists creates no entity, which is how a Crafty gets no fan mode and a Volcano gets no boost temperature. `tests/test_entities_by_family.py` pins the exact entity set of each family, so an entity leaking into the wrong family fails there. Commands go through `getattr(coordinator, "set_" + key)`, so a new writable key needs a `set_<key>` on the coordinator and a matching `async_set_<key>` on the devices that support it (the base class default raises `UnsupportedCommandError`, which `_async_command` turns into the `not_supported` exception).

### Update flow (push, not poll)

The integration is `local_push`: BLE notifications call back into the device, which calls `coordinator.async_update_listeners()`. The coordinator's 10s `update_interval` is only a reconnect/fallback poll, and a bluetooth-discovery callback triggers immediate connect attempts when the device is seen. Availability is connection state: `async_update_listeners` overrides `last_update_success` with `is_connected`. Setup never blocks on the device: `async_setup_entry` calls `coordinator.async_register_callbacks()` (installs the advertisement callback), forwards the platforms, then runs the first connect in a background task — so a slow cold-boot connect never gates Home Assistant startup, and an unreachable device just connects later when its advertisement arrives. The Crafty, Venty and Veazy switch Bluetooth off when idle, so they are simply unavailable until they advertise again.

The Venty and Veazy do not push state changes. `QvapDevice` runs a poll task while connected: it asks for status every `QVAP_POLL_INTERVAL` (1 s) and refreshes the slow-moving frames every 30th tick (nothing is sent while the device is not confirmed out of its bootloader); the task is cancelled on disconnect. A pending write is confirmed by the very next status reply. Until the device has confirmed it is not in its bootloader (`data.bootloader_mode is False`), `QvapDevice` refuses every command except the firmware query, and it never sends `0x0C` or `0x30` at all.

### Pending-write tracking (the subtle part)

Each tracked field on a `DeviceData` (fan, heater and set-temperature on the Volcano; heater and set-temperature plus the family's other writable fields elsewhere) is a `TrackedValue` in `data.py`, holding the last value the device confirmed and a pending write:

- A write is recorded **before** the GATT write is sent, because the device's confirming notification can arrive before the write call returns. Recording after caused a regression where a stale "off" write was replayed when the user turned the device on physically (see `test_physical_turn_on_is_not_reverted`).
- Setting the confirmed value clears the matching pending write when the device confirms it; `is_assumed` (exposed as `assumed_state` on the climate entity) is true while a write is unconfirmed.
- `_async_try_ensure_written_values` replays unconfirmed writes on each update — but drops all pending writes when the device is off, so queued commands never turn the device on unexpectedly.

The existing accessors (`fan_write`/`fan`, `heater_write`/`heater`, `set_temp_write`/`set_temp`) are thin views over those `TrackedValue`s; the semantics are unchanged.

Commands flow entity → `coordinator.set_*` → `_async_command`, which converts failures into `HomeAssistantError` with translation keys from `strings.json` (`exceptions` section).

### Adding a device family

1. **Data class** — subclass `DeviceData` in `volcano_ble/` (`<family>_data.py`): declare `capabilities` (a set of `VolcanoSensor` keys), the parsed fields, and a `TrackedValue` for each writable field.
2. **Device class** — subclass `StorzBickelDevice`: implement `family`, `data_class`, `_async_read_initial()`, `_async_refresh()`, `_async_try_ensure_written_values()` and override the `async_set_*` methods the family supports (the base defaults raise `UnsupportedCommandError`). Put pure frame building/parsing in its own module so it is testable without a client.
3. **Registry** — add the family to `DeviceFamily` and `detect_family()` in `const.py`, to `DEVICE_CLASSES` in `families.py`, and to the `bluetooth` matchers in `manifest.json`.
4. **Keys** — add any new `VolcanoSensor` keys, plus `set_<key>` wrappers on the coordinator for new writable ones.
5. **Platform rows** — add description rows (with the key in the data class's `capabilities`) to the platforms that should expose them.
6. **Strings and icons** — `strings.json` and `translations/en.json` (kept in sync by hand), and `icons.json`.
7. **Golden test** — add the family's entity set to `GOLDEN_ENTITIES` in `tests/test_entities_by_family.py`, and extend `FakeDevice` / the `device_family` fixture if entity tests need it.
8. **Spec document** — write `<FAMILY>_BLE_SPEC.md` with confidence tags, and add the protocol modules to `tests/test_spec_traceability.py`. If the family has a firmware endpoint, add it to `LATEST_KNOWN_FIRMWARE` and `scripts/check_firmware.py`. Update the README (supported-devices table, mark untested devices as such) and CHANGELOG.

### Translations

`strings.json` and `translations/en.json` must be kept in sync manually. Icons live in `icons.json`.

## Tests

`tests/` uses `pytest-homeassistant-custom-component` (asyncio_mode auto). Two levels of fakes:

- `FakeDevice(family)` (`tests/__init__.py`, alias `FakeVolcanoBLE`) replaces the whole protocol layer via the `mock_volcano` fixture — used by entity/coordinator/init tests. The `device_family` fixture picks the family (default Volcano Hybrid; parametrize it indirectly for another), and the `init_integration` fixture sets up a full config entry for that family against the fake.
- `tests/fakes.py` fakes the layer below: `FakeBleakClient` stands in for the bleak client and `SimulatedQvap` plays a Venty/Veazy on top of it (answering frames the way the spec says, in or out of its bootloader). They are used to test the protocol layer, including notification races and pending-write replay.

Two tests guard structure rather than behaviour: `tests/test_entities_by_family.py` pins the exact entity set each family creates (`GOLDEN_ENTITIES`), and `tests/test_spec_traceability.py` ties the protocol constants to the spec documents.

`conftest.py`'s `enable_bluetooth` fixture wraps the upstream one to cancel a lingering scanner timer that would otherwise trip HA's lingering-timer check — keep using it (via `init_integration`) for any test that loads the integration.
