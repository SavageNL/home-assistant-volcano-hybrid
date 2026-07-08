# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A HACS custom integration for Home Assistant that controls a Storz & Bickel Volcano Hybrid vaporizer over Bluetooth LE. It declares `quality_scale: platinum` in the manifest; `custom_components/volcano_hybrid/quality_scale.yaml` documents the status of every quality-scale rule. Changes should not regress any rule (strict typing, full config-flow test coverage, `PARALLEL_UPDATES` in every platform, translated exceptions, etc.).

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

## Architecture

Two layers, deliberately separated:

- `custom_components/volcano_hybrid/volcano_ble/` — protocol layer, no Home Assistant imports (only bleak/habluetooth). `VolcanoBLE` owns the GATT connection, parses characteristics into `VolcanoHybridData`, and subscribes to notifications. `VolcanoHybridData` is the single state object shared with the HA layer.
- `custom_components/volcano_hybrid/` — HA layer. `VolcanoHybridCoordinator` (in `coordinator.py`) wraps `VolcanoBLE`; entities are thin `CoordinatorEntity` subclasses of `VolcanoHybridEntity` (`entity.py`), which derives unique IDs as `{address}-{description.key}` and supports an `always_available` flag for diagnostic entities (RSSI, connected) that must outlive the connection.

### Update flow (push, not poll)

The integration is `local_push`: BLE notifications call back into `VolcanoBLE`, which calls `coordinator.async_update_listeners()`. The coordinator's 10s `update_interval` is only a reconnect/fallback poll, and a bluetooth-discovery callback triggers immediate connect attempts when the device is seen. Availability is connection state: `async_update_listeners` overrides `last_update_success` with `is_connected`. Setup never fails on an unreachable device — `async_config_entry_first_refresh` swallows `ConfigEntryNotReady` and connects later.

### Pending-write tracking (the subtle part)

`VolcanoHybridData` keeps write/state pairs (`fan_write`/`fan`, `heater_write`/`heater`, `set_temp_write`/`set_temp`):

- A write is recorded **before** the GATT write is sent, because the device's confirming notification can arrive before the write call returns. Recording after caused a regression where a stale "off" write was replayed when the user turned the device on physically (see `test_physical_turn_on_is_not_reverted`).
- State setters clear the matching pending write when the device confirms it; `is_assumed` (exposed as `assumed_state` on the climate entity) is true while a write is unconfirmed.
- `_async_try_ensure_written_values` replays unconfirmed writes on each update — but drops all pending writes when the device is off, so queued commands never turn the device on unexpectedly.

Commands flow entity → `coordinator.set_*` → `_async_command`, which converts failures into `HomeAssistantError` with translation keys from `strings.json` (`exceptions` section).

### Translations

`strings.json` and `translations/en.json` must be kept in sync manually. Icons live in `icons.json`.

## Tests

`tests/` uses `pytest-homeassistant-custom-component` (asyncio_mode auto). Two levels of fakes:

- `FakeVolcanoBLE` (`tests/__init__.py`) replaces the whole protocol layer via the `mock_volcano` fixture — used by entity/coordinator/init tests. The `init_integration` fixture sets up a full config entry against it.
- `FakeBleakClient` (`tests/test_volcano_ble.py`) fakes the bleak client itself — used to test the protocol layer, including notification races and pending-write replay.

`conftest.py`'s `enable_bluetooth` fixture wraps the upstream one to cancel a lingering scanner timer that would otherwise trip HA's lingering-timer check — keep using it (via `init_integration`) for any test that loads the integration.
