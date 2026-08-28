# Multi-device support — design

**Date:** 2026-08-28
**Status:** approved design, awaiting implementation plan
**Protocol references:** [`VOLCANO_BLE_SPEC.md`](../../../VOLCANO_BLE_SPEC.md),
[`CRAFTY_BLE_SPEC.md`](../../../CRAFTY_BLE_SPEC.md), [`VENTY_BLE_SPEC.md`](../../../VENTY_BLE_SPEC.md)

## 1. Goal

Make the `volcano_hybrid` integration control every device the Storz & Bickel web app
controls — Volcano Hybrid, Crafty / Crafty+, Venty and Veazy — in the same way the Volcano is
controlled today: Bluetooth discovery, one config entry per device, a climate entity plus
sensors/switches/numbers/buttons, pending-write tracking, auto-connect and reconnect
controls, diagnostics, and the platinum-scale rules the repository already holds itself to.

### Constraints that shape everything below

- **No hardware for the new devices.** Only the vendor web app and two community projects
  (storz-rs, verified on a Venty; reactive-volcano-app) are available. Correctness is
  established by unit tests against fakes built from the spec documents, and every shipped
  claim about a new device is labelled *untested on hardware*.
- **The domain stays `volcano_hybrid`.** Entity unique ids, config entries and the HACS
  installation must survive unchanged. Only user-facing labels change.
- **The Volcano must not regress.** Its behaviour, entity set and test-suite are the
  reference; the refactor that makes room for the other devices has to leave all of it
  passing.
- **All three device families ship in one implementation plan** (user decision), each
  clearly marked experimental in README and CHANGELOG.

### Non-goals

- Firmware flashing (see `VOLCANO_BLE_SPEC.md` §6.2).
- The vendor's *analysis* upload, and anything else that talks to Storz & Bickel's server
  from the integration.
- Boost / superboost as writable climate presets on Venty (writing heater modes 2/3 is
  SPECULATIVE) — read-only until observed.
- Writing the auto-off countdown on Venty (SPECULATIVE).
- Factory reset (destructive; CONFIRMED but deliberately not exposed).
- Renaming the repository or the HACS entry.

## 2. Architecture

Two layers as today; the change is that both become generic over a *device family*.

```
custom_components/volcano_hybrid/
├── volcano_ble/                  protocol layer, no HA imports
│   ├── const.py                  DeviceFamily, detect_family(), VolcanoSensor keys, limits
│   ├── data.py                   DeviceData base, TrackedValue, capabilities
│   ├── volcano_hybrid_data.py    VolcanoHybridData(DeviceData)         (kept)
│   ├── crafty_data.py            CraftyData(DeviceData)
│   ├── qvap_data.py              QvapData(DeviceData)                  (Venty + Veazy)
│   ├── device.py                 StorzBickelDevice base, create_device()
│   ├── volcano_ble.py            VolcanoDevice(StorzBickelDevice)      (kept path; VolcanoBLE alias)
│   ├── crafty.py                 CraftyDevice
│   ├── qvap_frames.py            pure frame build/parse for the Qvap protocol
│   └── qvap.py                   QvapDevice, poll task
├── coordinator.py                generic over the device (class name kept)
├── config_flow.py                family detection, VERSION 2, migration
├── entity.py                     unchanged
├── <platform>.py                 description tables filtered by data.capabilities
├── firmware.py                   per-family latest-known firmware
└── ...
```

### 2.1 `DeviceFamily` and detection (`volcano_ble/const.py`)

```python
class DeviceFamily(StrEnum):
    VOLCANO_HYBRID = "volcano_hybrid"
    CRAFTY = "crafty"        # Crafty and Crafty+, told apart later by firmware
    VENTY = "venty"
    VEAZY = "veazy"
```

`detect_family(service_info) -> DeviceFamily | None` decides from the advertisement, in this
order: name contains `VOLCANO H` and manufacturer id `1736` → Volcano; name contains
`S&B VY` → Venty; `S&B VZ` → Veazy; Qvap service UUID `00000000-5354-…` advertised and
neither → `None` (unknown Qvap device: refuse rather than guess); name starts with
`STORZ&BICKEL` / `Storz&Bickel` or any Crafty service UUID advertised → Crafty.
`is_supported(service_info)` is `detect_family(...) is not None`. Model names for the device
registry come from a `FAMILY_MODEL_NAME` mapping; the Crafty entry is refined to `Crafty+`
once the firmware major version is known to be ≥ 3.

### 2.2 Data model (`volcano_ble/data.py`)

`TrackedValue[T]` replaces the three hand-written write/state pairs. It has `value`
(device-confirmed), `pending` (last write not yet confirmed), `state` (pending if set else
value), `needs_write`, `record(write)` (called **before** the GATT write) and `confirm(value)`
(clears `pending` when it matches). The semantics are exactly the current ones; the point is
that Crafty and Qvap reuse them without copying the subtle parts.

`DeviceData` (base) holds what every family has:

| Field | Type | Notes |
|---|---|---|
| `current_temp` | `int \| None` | validated against the family's min/max |
| `set_temp` | `TrackedValue[int]` | |
| `heater` | `TrackedValue[bool]` | |
| `at_temperature` | `bool \| None` | the device's own ready bit |
| `serial_number`, `firmware_version`, `firmware_ble_version`, `bootloader_version` | `str \| None` | |
| `capabilities` | `frozenset[VolcanoSensor]` | class attribute per family |
| `min_temp`, `max_temp` | `int` | class attributes |

with the derived properties `is_on`, `is_assumed`, `is_heating` (heater on and current <
target) and the `get(key)` accessor the platforms use. `clear_open_writes()` drops every
pending value; the "never replay an on-command against a device that went off" rule lives in
each family's `_async_try_ensure_written_values`.

Family subclasses add their own fields (the full lists are in the spec documents and in §4
below). `VolcanoHybridData` keeps every existing field and property name so the Volcano
tests need no edits beyond fixture wiring.

**Capabilities are static per family.** An old-firmware Crafty (< V02.51) is not a separate
family: its unsupported commands raise the new translated `not_supported` error and its
unreadable values stay `None`. README documents it as monitor-only.

### 2.3 Device base class (`volcano_ble/device.py`)

`StorzBickelDevice(VolcanoHybridDataStatusProvider)` owns: the connect lock and
`establish_connection` call, the disconnected callback, RSSI and connected-address
properties with their change notifications, `_get_characteristic`,
`_async_read_and_subscribe`, `_write_gatt`, `async_disconnect`, and the
`async_manual_update()` template:

```
async_manual_update(device):
    swap device if a different BLEDevice was handed in
    await _ensure_client_connected()      # → _async_connect → _async_read_initial()
    await _async_refresh()                # family hook: re-read what a dropped notify would stale
    await _async_try_ensure_written_values()
```

Abstract hooks: `family`, `data`, `_async_read_initial()`, `_async_refresh()`,
`_async_try_ensure_written_values()`, plus an `_on_disconnected()` hook so Qvap can stop its
poll task. `create_device(family, data_updated, device_updated)` returns the right subclass;
this is what the coordinator calls and what the tests patch.

`VolcanoDevice` is today's `VolcanoBLE` with the shared parts removed and **nothing else
changed**. The name `VolcanoBLE` stays importable as an alias for one release.

### 2.4 `CraftyDevice`

- Initial read/subscribe per `CRAFTY_BLE_SPEC.md` §7: subscribe current temp, battery,
  countdown, PRJSTAT1, PRJSTAT2; read target, boost, serial, firmware, BLE firmware,
  hours/minutes, LED, auto-off setting, system/battery status words. Characteristics that
  only exist on ≥ V02.51 are read after the firmware string and skipped on older firmware;
  a missing characteristic is tolerated, not fatal.
- Target read applies the "> 210 means °F" rule (§3.1). Target write is followed by the
  boost rewrite (§3.2). Auto-off write is preceded by security code `815` (§5.2).
- Heater on/off write two zero bytes to the respective characteristic; PRJSTAT1 bit 4
  confirms.
- PRJSTAT2 writes are read-modify-write of the whole word from the last known value,
  followed by a re-read.
- `_async_refresh()` re-reads current temperature and PRJSTAT1 (same reasoning as the
  Volcano's fallback poll).

### 2.5 `QvapDevice` and `qvap_frames`

`qvap_frames.py` is pure Python: `build_status_write(mask, **fields)`, `build_settings_write(
bits, mask, bits2, mask2)`, `build_cmd06(mask, brightness, vibration, timeout_disabled)`,
`parse_status(frame) -> StatusFrame`, `parse_firmware(frame)`, `parse_usage(frame)`,
`parse_identity(frame)`, `parse_cmd06(frame)`, `parse_advertising_info(frame)`. Each mirrors
one table in `VENTY_BLE_SPEC.md`; a frame shorter than its table says is rejected with
`ValueError`. A module-level `FORBIDDEN_COMMANDS = {0x0C, 0x30}` plus the bootloader
sub-commands of `0x01` are asserted against in `_write_frame`, which refuses to send them.

`QvapDevice`:

- On connect: `start_notify` on the control characteristic, then send `0x02`, `0x1D`,
  `0x01`, `0x04`, `0x05`, `0x06` (spec §4 minus the server-only steps), read the GAP name
  if present.
- Replies are dispatched by byte 0 into the parsers and applied to `QvapData`; `0x02` byte 1
  bit 0 clear sets `data.bootloader_mode = True`, which makes every control command raise
  `not_supported` until a later `0x02` clears it.
- **Poll task**: while connected, send `0x01` every `QVAP_POLL_INTERVAL = 1.0` s and `0x04`
  + `0x06` every 30th tick. Started at the end of the connect sequence, cancelled from
  `_on_disconnected()` and from `async_disconnect()`. Exceptions in the loop disconnect and
  stop the loop rather than spin.
- Writes: target (mask `0x02`), boost (`0x04`), superboost (`0x08`), heater on/off (`0x20`,
  byte 11 ∈ {0, 1}), settings bits (`0x80`, bytes 14–17), brightness/vibration/timeout
  (`0x06`). The very next `0x01` reply confirms; `_async_try_ensure_written_values` replays
  anything still pending, dropping all pending writes if heater mode is `0`.
- Veazy inverts the boost-visualisation bit in both directions; permanent-Bluetooth is
  writable on Veazy only. Both are keyed off `family`.

### 2.6 Coordinator

`VolcanoHybridCoordinator(hass, config_entry, address, family)`; `self.name` and
`device_info.model` come from the family. Everything else — advertisement callback with
scheduled connect, 10 s fallback poll, `auto_connect`, `reconnect`, `delayed_reconnect`,
`_async_command`, `update_device` — is unchanged and shared. `update_device` also updates
`model` (Crafty → Crafty+). New `set_*` methods are thin wrappers, one per writable field,
named after the `VolcanoSensor` key so the existing `getattr(coordinator, "set_" + key)`
convention in the switch/number platforms keeps working.

`_async_command` gains a third failure mapping: a device method may raise
`UnsupportedCommandError` (protocol layer) → `HomeAssistantError(translation_key="not_supported")`.

**Availability** stays "connected". Sleeping Crafty/Venty devices are *unavailable*, exactly
like a switched-off Volcano. Diagnostic entities marked `always_available` (RSSI, connected,
connected address, auto-connect, reconnect buttons, update) keep behaving as today.

### 2.7 Config flow and migration

- `manifest.json` `bluetooth` matchers: existing Volcano matcher plus
  `{"local_name": "S&B VY*"}`, `{"local_name": "S&B VZ*"}`,
  `{"service_uuid": "00000000-5354-4f52-5a26-4249434b454c"}`,
  `{"local_name": "STORZ&BICKEL*"}`, `{"local_name": "Storz&Bickel*"}`,
  `{"service_uuid": "00000001-4c45-4b43-4942-265a524f5453"}`. No manufacturer id for the new
  families (unknown, SPECULATIVE).
- Entry data: `{"address": ..., "model": DeviceFamily}`. `ConfigFlow.VERSION = 2`;
  `async_migrate_entry` adds `model = "volcano_hybrid"` to version-1 entries. Title is the
  advertised name. `_async_discover_devices` lists every supported family; the dropdown label
  shows `name (address)` as today. Reconfigure re-detects the family for the chosen address
  and rewrites `model`.
- `async_setup_entry` reads `model` and passes it to the coordinator.

### 2.8 Firmware tracking

`firmware.py`: `LATEST_KNOWN_FIRMWARE: dict[DeviceFamily, tuple[int, int] | None]` —
Volcano `(1, 3)`, Venty/Veazy `None` until somebody records one, Crafty absent (no update
entity). `latest_firmware_version(family, installed)` returns `None` when nothing is known
rather than echoing the installed version. `parse_firmware_version` already copes with the
Venty's `V01.09` strings. `scripts/check_firmware.py` and `firmware-check.yml` post
`device=Venty&action=version` and `device=Veazy&action=version` in addition to the Hybrid
call and label issues `firmware-watch:<family>-<status>`.

## 3. Entities

Each platform keeps a single description table keyed by `VolcanoSensor`; `async_setup_entry`
instantiates only the keys present in `coordinator.data.capabilities`. The Volcano's rows are
untouched.

| Platform | Volcano Hybrid | Crafty / Crafty+ | Venty / Veazy |
|---|---|---|---|
| climate | as today (fan mode; 40–230 °C) | target 40–210, HEAT/OFF, action heating/off | target 40–210, HEAT/OFF, action heating/off |
| number | shut-off (min), LED 0–100 | boost offset 1–99 °C, LED 0–100, auto-off 0–300 s | boost 1–99, superboost 1–99, brightness 1–9 |
| switch | as today + auto-connect | vibration, charge LED, auto BLE shutdown, auto-connect | Celsius display, vibration, charge optimisation, charge limit, boost visualisation, boost-timeout-disabled, auto-connect; permanent Bluetooth (Veazy only) |
| sensor | as today | battery %, auto-off countdown (s), heat time, RSSI, connected address, raw PRJSTAT1/PRJSTAT2/system/battery1/battery2 (hex, disabled by default) | battery %, auto-off countdown (s), heater mode (enum: off/heating/boost/superboost), heat time, charging time, RSSI, connected address, colour (Veazy, enum) |
| binary_sensor | as today | ready, heater, boost, superboost, error, needs factory reset, find-mode active, connected | ready, heater, charging, boost, superboost, target changed on device, bootloader mode, permanent Bluetooth (Venty, read-only), connected |
| button | reconnect, delayed reconnect | reconnect, delayed reconnect, find my device (Crafty+) | reconnect, delayed reconnect, find my device |
| update | as today | — | installed version; latest from the per-family constant |

Climate `hvac_action` for Crafty/Qvap: `HEATING` while `is_heating`, no action while holding
(same convention as the Volcano), `OFF` otherwise; there is no cooling inference (nothing to
base it on). `assumed_state` follows `is_assumed`.

Entity ids are `{address}-{key}` as today, so the Volcano's ids do not move. New keys are
added to `VolcanoSensor`, `strings.json`, `translations/en.json` and `icons.json`.

## 4. Error handling

| Situation | Behaviour |
|---|---|
| BLE write fails | `command_failed` (existing) |
| Device not connected | `not_connected` (existing) |
| Command the family/firmware/mode cannot do (old Crafty heater, Venty in bootloader) | new `not_supported` |
| Missing optional characteristic on connect (old Crafty) | logged at debug, value stays `None`, connect succeeds |
| Malformed Qvap frame | parser raises `ValueError`; the device logs at debug and ignores the frame; connection stays up |
| Poll task error | disconnect, task ends; the coordinator's normal reconnect path takes over |
| Unknown Qvap device name | not offered in discovery (`detect_family` → `None`) |

## 5. Testing

All tests run with `pytest-homeassistant-custom-component` in the Linux container; coverage
≥ 95 % overall and 100 % for `config_flow.py`; strict mypy; ruff `ALL`.

1. **Frame/decoder tests** (`tests/test_qvap_frames.py`, `tests/test_crafty_codec.py`) —
   byte-exact round trips for every builder/parser, with inputs derived from the vendor
   app's parsing rules (e.g. a status frame with `b2=0x2E, b3=0x07` parses to 183 °C; the
   Veazy visualisation inversion; the `> 210` Fahrenheit rule; security-code sequencing).
2. **Protocol-layer tests** with `FakeBleakClient` extended by a per-family characteristic
   table. For Qvap, a `SimulatedQvap` applies write masks to an internal state and answers
   each write with the full `0x01` frame via the notify callback, so poll loop, pending-write
   confirmation, bootloader-mode gating and the forbidden-command guard are all exercised.
   Volcano tests keep passing with only the fixture patch target changed.
3. **HA-layer tests** — `FakeVolcanoBLE` becomes `FakeDevice(family)` returning the matching
   data class; `init_integration` is parametrised by family. One golden test per family
   asserts the exact set of entity ids created, so a capability leaking between families
   fails. Existing per-platform tests stay Volcano-scoped; new families get the same shape
   of test for each new entity (state reflects data; command calls the right device method;
   failure maps to the right error).
4. **Config flow** — discovery, user, bluetooth-confirm, reconfigure and abort paths per
   family; `async_migrate_entry` v1 → v2.
5. **Spec traceability** — a test that every UUID and mask literal in `crafty.py` /
   `qvap_frames.py` appears verbatim in the corresponding `*_BLE_SPEC.md`, so the code and
   the reference cannot drift apart silently.

## 6. Documentation and metadata

- `README.md`: supported-devices table with *tested on hardware* (yes/no) and a request for
  testers; per-device entity list; a "sleeping devices" section explaining unavailability
  and the *auto BLE shutdown* / *permanent Bluetooth* settings; old-Crafty note.
- `CHANGELOG.md` `## [Unreleased]`: one entry per family, each tagged experimental.
- `CLAUDE.md`: architecture section rewritten for the family abstraction; the pending-write
  paragraph now points at `TrackedValue`; the three spec files listed.
- `manifest.json` `name` and `hacs.json` `name` → "Storz & Bickel"; `domain` unchanged.
- `quality_scale.yaml`: no rule changes; comments updated where they mention the Volcano
  only.

## 7. Risks and how they are contained

- **The decodes are wrong somewhere.** Certain for at least one SPECULATIVE row. Contained
  by: only CONFIRMED/STRONG features are exposed; every constant traces to a spec row; the
  experimental label; raw status sensors so a tester can report bits.
- **The Volcano refactor changes behaviour.** Contained by keeping the Volcano test-suite
  unchanged and green, and by moving code rather than rewriting it.
- **Qvap polling through an ESPHome proxy** at 1 s may be too chatty. Contained by making the
  interval a constant that is trivial to lift into options later; not exposed now (YAGNI).
- **Sleeping devices look "broken"** to users used to the Volcano. Contained by README and by
  the connected/RSSI diagnostics that stay available.
