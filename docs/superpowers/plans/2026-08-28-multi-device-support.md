# Multi-Device Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `volcano_hybrid` integration control Crafty / Crafty+, Venty and Veazy alongside the Volcano Hybrid, without changing anything the Volcano does today.

**Architecture:** The protocol layer gains a `StorzBickelDevice` base class with `VolcanoDevice`, `CraftyDevice` and `QvapDevice` (Venty + Veazy) subclasses, plus a `DeviceData` base carrying a static per-family `capabilities` set. One generic coordinator builds the right device from the family stored in the config entry; every platform instantiates only the entity keys the family declares.

**Tech Stack:** Python 3.14, Home Assistant custom integration (`pytest-homeassistant-custom-component`, asyncio_mode auto), bleak / bleak-retry-connector / habluetooth, ruff `ALL`, strict mypy.

**Spec:** `docs/superpowers/specs/2026-08-28-multi-device-support-design.md` — read it first; protocol tables are in `VOLCANO_BLE_SPEC.md`, `CRAFTY_BLE_SPEC.md`, `VENTY_BLE_SPEC.md`.

## Global Constraints

- Domain stays `volcano_hybrid`; entity unique ids stay `{address}-{key}`; the `VolcanoSensor` key enum and the `VolcanoHybridData` / `VolcanoHybridCoordinator` / `VolcanoHybridEntity` class names are kept.
- The Volcano's behaviour and entity set must not change. Existing tests may only be edited where this plan says so (fixture wiring, config-entry data shape).
- Tests and mypy run on Linux only. From Windows use the container from `CLAUDE.md`:
  `podman run --rm -v "<repo>:/workspace" -w /workspace python:3.14 sh -c "pip install -q -r requirements.txt && python -m pytest tests -q && mypy --config-file mypy.ini"`.
  Abbreviated below as **`RUN_TESTS <pytest args>`** (replace `python -m pytest tests -q` with the args) and **`RUN_LINT`** (`ruff format . && ruff check --fix . && mypy --config-file mypy.ini`, on a clean clone inside the container because NTFS bind mounts trip `EXE002`).
- Coverage ≥ 95 % overall, `config_flow.py` 100 %. `PARALLEL_UPDATES = 0` in every platform. Every user-facing string goes in `strings.json` **and** `translations/en.json` (en.json is the same content with keys sorted and 4-space indent). Every exception raised to HA uses a translation key under `exceptions`.
- Only CONFIRMED / STRONG features from the spec documents are exposed. Never send Qvap commands `0x0C` or `0x30`, or `0x01` while the device is in bootloader mode.
- Commit after every task. No session links in commit messages; keep `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- New devices are labelled "untested on hardware" in README and CHANGELOG.

## File structure

| File | Responsibility |
|---|---|
| `volcano_ble/const.py` | `DeviceFamily`, `FAMILY_MODEL_NAME`, `detect_family`, discovery UUIDs, `VolcanoSensor` keys, temperature limits |
| `volcano_ble/data.py` | `TrackedValue`, `DeviceData`, `VolcanoHybridDataStatusProvider` |
| `volcano_ble/volcano_hybrid_data.py` | `VolcanoHybridData(DeviceData)` — existing fields, unchanged API |
| `volcano_ble/crafty_data.py` | `CraftyData(DeviceData)` + pure decoders |
| `volcano_ble/qvap_frames.py` | pure Qvap frame builders/parsers |
| `volcano_ble/qvap_data.py` | `QvapData`, `VentyData`, `VeazyData` |
| `volcano_ble/device.py` | `StorzBickelDevice`, `UnsupportedCommandError`, default `async_set_*` stubs |
| `volcano_ble/families.py` | `DATA_CLASSES`, `DEVICE_CLASSES`, `create_device` — the registry to extend per family |
| `volcano_ble/volcano_ble.py` | `VolcanoDevice` (today's code minus the shared parts), `VolcanoBLE` alias |
| `volcano_ble/crafty.py` | `CraftyDevice` |
| `volcano_ble/qvap.py` | `QvapDevice` + poll task |
| `coordinator.py` | generic over family; `set_*` per writable key |
| `config_flow.py` / `__init__.py` | family detection, `CONF_MODEL`, VERSION 2 + migration |
| `<platform>.py` | description tables + capability filtering |
| `firmware.py`, `update.py`, `scripts/check_firmware.py`, `.github/workflows/firmware-check.yml` | per-family firmware tracking |
| `tests/__init__.py` | `FakeDevice(family)` (replaces `FakeVolcanoBLE`, name kept as alias), service-info builders per family |
| `tests/test_qvap_frames.py`, `tests/test_crafty_data.py`, `tests/test_crafty_ble.py`, `tests/test_qvap_ble.py`, `tests/test_entities_by_family.py`, `tests/test_spec_traceability.py` | new tests |

---

### Task 1: `TrackedValue` and the `DeviceData` base

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/data.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/volcano_hybrid_data.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/const.py` (add `DeviceFamily`, limits)
- Test: `tests/test_data.py` (new), `tests/test_volcano_hybrid_data.py` (must pass unchanged)

**Interfaces:**
- Produces `TrackedValue[T]` with `value`, `pending`, `state`, `needs_write`, `clear()`.
- Produces `DeviceData(device)` with class attrs `family: DeviceFamily`, `capabilities: frozenset[str]`, `MIN_TEMP: int`, `MAX_TEMP: int`, `MIN_DISPLAY_TEMP: int`; properties `current_temp`, `set_temp`/`set_temp_write`/`set_temp_state`/`set_temp_needs_write`, `heater`/`heater_write`/`heater_state`/`heater_needs_write`, `at_temperature`, `serial_number`, `firmware_version`, `firmware_ble_version`, `bootloader_version`, `is_on`, `is_assumed`, `is_heating`, `is_cooling` (False), `model_name`, `connected`, `rssi`, `connected_addr`, `clear_open_writes()`, `get(key)`.
- `DeviceFamily` enum values: `volcano_hybrid`, `crafty`, `venty`, `veazy`.

- [ ] **Step 1: Add `DeviceFamily` and limits to `volcano_ble/const.py`**

Append after the existing constants (keep everything already there):

```python
class DeviceFamily(StrEnum):
    """The Storz & Bickel device families this integration speaks to."""

    VOLCANO_HYBRID = "volcano_hybrid"
    # Crafty and Crafty+ share a protocol; the model is told apart by the
    # firmware major version after connecting (CRAFTY_BLE_SPEC.md §6).
    CRAFTY = "crafty"
    VENTY = "venty"
    VEAZY = "veazy"


# How each family is named in the device registry until it says otherwise.
FAMILY_MODEL_NAME: dict[DeviceFamily, str] = {
    DeviceFamily.VOLCANO_HYBRID: "Volcano Hybrid",
    DeviceFamily.CRAFTY: "Crafty",
    DeviceFamily.VENTY: "Venty",
    DeviceFamily.VEAZY: "Veazy",
}

# Portable devices: the app clamps the target to 40–210 °C for both families
# (CRAFTY_BLE_SPEC.md §3, VENTY_BLE_SPEC.md §5).
PORTABLE_MIN_TEMP = 0
PORTABLE_MAX_TEMP = 210
PORTABLE_MIN_DISPLAY_TEMP = 40
```

- [ ] **Step 2: Write the failing tests for `TrackedValue` and the base data**

Create `tests/test_data.py`:

```python
"""Tests for the pending-write tracking shared by every device family."""

from __future__ import annotations

from custom_components.volcano_hybrid.volcano_ble.const import DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.data import DeviceData, TrackedValue

from . import FakeVolcanoBLE


def test_tracked_value_records_before_confirmation() -> None:
    """A pending write drives the state until the device confirms it."""
    tracked: TrackedValue[bool] = TrackedValue()
    assert tracked.state is None
    assert not tracked.needs_write

    tracked.pending = True
    assert tracked.state is True
    assert tracked.value is None
    assert tracked.needs_write

    tracked.value = True
    assert tracked.pending is None
    assert tracked.state is True
    assert not tracked.needs_write


def test_tracked_value_matching_the_device_never_goes_pending() -> None:
    """A write equal to the confirmed value is dropped, so it cannot be replayed."""
    tracked: TrackedValue[int] = TrackedValue()
    tracked.value = 180
    tracked.pending = 180
    assert tracked.pending is None
    assert not tracked.needs_write


def test_tracked_value_stays_pending_while_the_device_disagrees() -> None:
    """The device reporting another value keeps the write pending."""
    tracked: TrackedValue[int] = TrackedValue()
    tracked.value = 180
    tracked.pending = 190
    tracked.value = 185
    assert tracked.needs_write
    assert tracked.state == 190

    tracked.clear()
    assert tracked.pending is None
    assert tracked.state == 185


def test_base_data_defaults() -> None:
    """A bare data object claims nothing before the device has reported."""
    data = FakeVolcanoBLE().data
    assert isinstance(data, DeviceData)
    assert data.family is DeviceFamily.VOLCANO_HYBRID
    assert data.model_name == "Volcano Hybrid"
    assert data.is_heating is None
    assert not data.is_assumed
    assert "at_temperature" in data.capabilities
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `RUN_TESTS tests/test_data.py -q`
Expected: FAIL — `ModuleNotFoundError: ... volcano_ble.data`

- [ ] **Step 4: Create `volcano_ble/data.py`**

```python
"""State shared by every Storz & Bickel device, and how pending writes are tracked."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from .const import FAMILY_MODEL_NAME, DeviceFamily

T = TypeVar("T")


class VolcanoHybridDataStatusProvider:
    """Interface to retrieve Device data from the Data."""

    @property
    def rssi(self) -> int | None:
        """Get the device rssi."""
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        """Determine whether the device is connected."""
        raise NotImplementedError

    @property
    def connected_addr(self) -> str | None:
        """Get the connected mac address."""
        raise NotImplementedError


class TrackedValue(Generic[T]):
    """
    A device value together with the last write not yet confirmed for it.

    The write is recorded *before* it is sent, because the device's confirming
    notification can arrive before the GATT write call returns
    (VOLCANO_BLE_SPEC.md §5). A write that matches what the device already
    reports is dropped on the spot so it can never be replayed later.
    """

    def __init__(self) -> None:
        """Start with nothing read and nothing pending."""
        self._value: T | None = None
        self._pending: T | None = None

    @property
    def value(self) -> T | None:
        """The value the device last confirmed."""
        return self._value

    @value.setter
    def value(self, value: T | None) -> None:
        self._value = value
        if self._pending is not None and self._pending == value:
            self._pending = None

    @property
    def pending(self) -> T | None:
        """The write still waiting for the device to confirm it."""
        return self._pending

    @pending.setter
    def pending(self, value: T | None) -> None:
        self._pending = None if value == self._value else value

    @property
    def state(self) -> T | None:
        """What the entity should show: the pending write, else the value."""
        return self._pending if self._pending is not None else self._value

    @property
    def needs_write(self) -> bool:
        """Whether a pending write still has to be (re)sent."""
        return self._pending is not None and self._pending != self._value

    def clear(self) -> None:
        """Drop the pending write."""
        self._pending = None


class DeviceData:
    """What every family reports: temperatures, the heater, identity."""

    family: DeviceFamily
    # The entity keys (VolcanoSensor values) the family supports. Static per
    # family: what a device cannot do fails with `not_supported` rather than
    # changing the entity set after setup.
    capabilities: frozenset[str] = frozenset()
    MIN_TEMP = 0
    MAX_TEMP = 230
    MIN_DISPLAY_TEMP = 40

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the shared fields."""
        self.device = device
        self._current_temp: int | None = None
        self._set_temp: TrackedValue[int] = TrackedValue()
        self._heater: TrackedValue[bool] = TrackedValue()
        self._tracked: list[TrackedValue[Any]] = [self._set_temp, self._heater]

        self.serial_number: str | None = None
        self.firmware_version: str | None = None
        self.firmware_ble_version: str | None = None
        self.bootloader_version: str | None = None
        # The device's own "setpoint reached" signal.
        self.at_temperature: bool | None = None

    # -- identity --------------------------------------------------------

    @property
    def model_name(self) -> str:
        """The model to show in the device registry."""
        return FAMILY_MODEL_NAME[self.family]

    # -- derived state ---------------------------------------------------

    @property
    def is_assumed(self) -> bool:
        """Whether any write is still waiting for confirmation."""
        return any(tracked.needs_write for tracked in self._tracked)

    @property
    def is_on(self) -> bool:
        """Whether the device is doing anything."""
        return bool(self.heater)

    @property
    def is_heating(self) -> bool | None:
        """Whether the heater is working towards a setpoint it has not reached."""
        heater = self.heater_state
        if heater is None:
            return None
        if not heater:
            return False
        if self.current_temp is None or self.set_temp_state is None:
            return None
        return self.current_temp < self.set_temp_state

    @property
    def is_cooling(self) -> bool:
        """Whether the device is still cooling down; only the Volcano infers this."""
        return False

    def clear_open_writes(self) -> None:
        """Remove all open writes."""
        for tracked in self._tracked:
            tracked.clear()

    # -- temperatures ----------------------------------------------------

    @property
    def current_temp(self) -> int | None:
        """Get the current temp."""
        if self._current_temp is not None and self._current_temp > 0:
            return self._current_temp
        return None

    @current_temp.setter
    def current_temp(self, value: int) -> None:
        if self.MIN_TEMP <= value <= self.MAX_TEMP:
            self._current_temp = value
        else:
            self._current_temp = None

    @property
    def set_temp(self) -> int | None:
        """Return the confirmed target temperature."""
        return self._set_temp.value

    @set_temp.setter
    def set_temp(self, value: int) -> None:
        self._set_temp.value = value

    @property
    def set_temp_write(self) -> int | None:
        """Return the pending target write."""
        return self._set_temp.pending

    @set_temp_write.setter
    def set_temp_write(self, value: int | None) -> None:
        self._set_temp.pending = value

    @property
    def set_temp_state(self) -> int | None:
        """Return the target as it should be shown."""
        return self._set_temp.state

    @property
    def set_temp_needs_write(self) -> bool:
        """Check if the target needs to be written."""
        return self._set_temp.needs_write

    # -- heater ----------------------------------------------------------

    @property
    def heater(self) -> bool | None:
        """Return the confirmed heater state."""
        return self._heater.value

    @heater.setter
    def heater(self, value: bool) -> None:
        self._heater.value = value

    @property
    def heater_write(self) -> bool | None:
        """Return the pending heater write."""
        return self._heater.pending

    @heater_write.setter
    def heater_write(self, value: bool | None) -> None:
        self._heater.pending = value

    @property
    def heater_state(self) -> bool | None:
        """Return the heater state as it should be shown."""
        return self._heater.state

    @property
    def heater_needs_write(self) -> bool:
        """Check if the heater needs to be written."""
        return self._heater.needs_write

    # -- connection ------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the device is connected."""
        return self.device.is_connected

    @property
    def rssi(self) -> int | None:
        """The current rssi."""
        return self.device.rssi

    @property
    def connected_addr(self) -> str | None:
        """The adapter the device is connected through."""
        return self.device.connected_addr

    def get(self, key: str) -> Any | None:
        """Get the value of the specified key."""
        return getattr(self, key)
```

- [ ] **Step 5: Rebase `VolcanoHybridData` on `DeviceData`**

In `volcano_hybrid_data.py`: delete the `VolcanoHybridDataStatusProvider` class and re-export it (`from .data import DeviceData, TrackedValue, VolcanoHybridDataStatusProvider`; add `VolcanoHybridDataStatusProvider` to `__all__` so `tests/__init__.py` keeps importing it from here). Change `class VolcanoHybridData:` to `class VolcanoHybridData(DeviceData):` with class attrs:

```python
    family = DeviceFamily.VOLCANO_HYBRID
    MIN_TEMP = VOLCANO_HYBRID_MIN_TEMP
    MAX_TEMP = VOLCANO_HYBRID_MAX_TEMP
    MIN_DISPLAY_TEMP = 40
    capabilities = frozenset(
        {
            VolcanoSensor.VOLCANO, VolcanoSensor.FIRMWARE,
            VolcanoSensor.CURRENT_AUTO_OFF_TIME, VolcanoSensor.CURRENT_ON_TIME,
            VolcanoSensor.HEAT_TIME, VolcanoSensor.SHUT_OFF, VolcanoSensor.LED_BRIGHTNESS,
            VolcanoSensor.AUTO_SHUTDOWN, VolcanoSensor.AT_TEMPERATURE,
            VolcanoSensor.HEATER_ACTIVE, VolcanoSensor.PUMP_ACTIVE,
            VolcanoSensor.ACTUATOR_FAULT, VolcanoSensor.PRV1_ERROR,
            VolcanoSensor.SHOWING_CELSIUS, VolcanoSensor.DISPLAY_ON_COOLING,
            VolcanoSensor.SERVICE_MODE, VolcanoSensor.PRV2_ERROR, VolcanoSensor.VIBRATION,
            VolcanoSensor.RECONNECT, VolcanoSensor.DELAYED_RECONNECT,
            VolcanoSensor.AUTO_CONNECT, VolcanoSensor.CONNECTED, VolcanoSensor.RSSI,
            VolcanoSensor.CONNECTED_ADDR, VolcanoSensor.MAINS_VOLTAGE,
            VolcanoSensor.PRJ1, VolcanoSensor.PRJ2, VolcanoSensor.PRJ3,
            VolcanoSensor.PRJ4, VolcanoSensor.PRJ5, VolcanoSensor.HIST1,
            VolcanoSensor.HIST2, VolcanoSensor.LAST_FAULT,
        }
    )
```

In `__init__`: call `super().__init__(device)`, delete `self._current_temp`, `self._set_temp`, `self._set_temp_write`, `self._heater`, `self._heater_write`, `self.serial_number`, `self.firmware_version`, `self.firmware_ble_version`, `self.bootloader_version`, `self.at_temperature` (all now in the base). Replace `self._fan: bool | None = None` and `self._fan_write` with `self._fan: TrackedValue[bool] = TrackedValue()` and `self._tracked.append(self._fan)`.

Delete these members (the base provides them): `is_assumed`, `clear_open_writes`, `heater_write`, `set_temp_write`, `heater_state`, `heater`, `heater_needs_write`, `set_temp_state`, `set_temp`, `set_temp_needs_write`, `connected`, `rssi`, `connected_addr`, `current_temp` (getter + setter), `get`, and the `is_heating` property (its docstring moves onto the base's `is_heating`; copy the Volcano explanation there verbatim).

Rewrite the fan members onto the tracked value:

```python
    @property
    def fan_write(self) -> bool | None:
        """Return the pending fan write."""
        return self._fan.pending

    @fan_write.setter
    def fan_write(self, value: bool | None) -> None:
        self._fan.pending = value

    @property
    def fan_state(self) -> bool | None:
        """Return the fan as it should be shown."""
        return self._fan.state

    @property
    def fan(self) -> bool | None:
        """Return the confirmed fan state."""
        return self._fan.value

    @fan.setter
    def fan(self, value: bool) -> None:
        self._fan.value = value

    @property
    def fan_needs_write(self) -> bool:
        """Check if the fan needs to be written."""
        return self._fan.needs_write

    @property
    def is_on(self) -> bool:
        """Check if the device is on."""
        return bool(self.fan or self.heater)
```

Add the model-name rendering that today lives in `coordinator._model_name`:

```python
    @property
    def model_name(self) -> str:
        """
        Render the model the device reports as the name people know it by.

        (docstring of coordinator._model_name, moved here verbatim)
        """
        if not self.model or not self.model.isalpha():
            return FAMILY_MODEL_NAME[self.family]
        return f"Volcano {self.model.capitalize()}"
```

Import `DeviceFamily`, `FAMILY_MODEL_NAME`, `VolcanoSensor` from `.const`.

- [ ] **Step 6: Run the data tests**

Run: `RUN_TESTS tests/test_data.py tests/test_volcano_hybrid_data.py tests/test_volcano_ble.py -q`
Expected: PASS (the Volcano tests exercise the same properties through the new tracked values).

- [ ] **Step 7: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests/test_data.py
git commit -m "Track pending writes with one helper shared by every device family"
```

---

### Task 2: Family detection from the advertisement

**Files:**
- Modify: `custom_components/volcano_hybrid/volcano_ble/const.py`
- Test: `tests/test_detect_family.py` (new); `tests/__init__.py` (add builders)

**Interfaces:**
- Produces `detect_family(service_info: BluetoothServiceInfoBleak) -> DeviceFamily | None`, `is_supported(service_info) -> bool`, constants `STORZ_BICKEL_MANUFACTURER_ID = 1736`, `QVAP_SERVICE_UUID`, `CRAFTY_SERVICE_UUIDS`.
- Test helpers in `tests/__init__.py`: `CRAFTY_NAME = "STORZ&BICKEL"`, `VENTY_NAME = "S&B VY123456"`, `VEAZY_NAME = "S&B VZ654321"`, and `make_service_info(..., service_uuids: list[str] | None = None)`.

- [ ] **Step 1: Extend `make_service_info` in `tests/__init__.py`**

Add a `service_uuids: list[str] | None = None` parameter and pass `service_uuids=service_uuids or []` to both `AdvertisementData` and `BluetoothServiceInfoBleak`. Add the three name constants next to `VOLCANO_NAME`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_detect_family.py`:

```python
"""Tests for telling the device families apart from their advertisements."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble.const import (
    CRAFTY_SERVICE_UUIDS,
    QVAP_SERVICE_UUID,
    DeviceFamily,
    detect_family,
    is_supported,
)

from . import CRAFTY_NAME, VEAZY_NAME, VENTY_NAME, VOLCANO_NAME, make_service_info


@pytest.mark.parametrize(
    ("name", "manufacturer_id", "service_uuids", "expected"),
    [
        (VOLCANO_NAME, 1736, [], DeviceFamily.VOLCANO_HYBRID),
        # A Volcano needs the manufacturer id: the name alone is not enough.
        (VOLCANO_NAME, 76, [], None),
        (VENTY_NAME, 76, [], DeviceFamily.VENTY),
        (VEAZY_NAME, 76, [], DeviceFamily.VEAZY),
        # The Qvap service without a known name is refused, not guessed.
        ("S&B XX000000", 76, [QVAP_SERVICE_UUID], None),
        (CRAFTY_NAME, 76, [], DeviceFamily.CRAFTY),
        ("Storz&Bickel", 76, [], DeviceFamily.CRAFTY),
        ("Unnamed", 76, [CRAFTY_SERVICE_UUIDS[0]], DeviceFamily.CRAFTY),
        ("OTHER DEVICE", 76, [], None),
        ("S&B CRAFTY 123", 1736, [], None),
    ],
)
def test_detect_family(
    name: str,
    manufacturer_id: int,
    service_uuids: list[str],
    expected: DeviceFamily | None,
) -> None:
    """Each family is recognised by what its advertisement carries."""
    info = make_service_info(
        name=name, manufacturer_id=manufacturer_id, service_uuids=service_uuids
    )
    assert detect_family(info) is expected
    assert is_supported(info) is (expected is not None)


def test_detect_family_without_a_name() -> None:
    """A nameless advertisement is only a Crafty if it carries the service."""
    info = make_service_info(name="", manufacturer_id=76)
    assert detect_family(info) is None
```

- [ ] **Step 3: Run to verify failure**

Run: `RUN_TESTS tests/test_detect_family.py -q`
Expected: FAIL — `ImportError: cannot import name 'detect_family'`

- [ ] **Step 4: Implement detection in `volcano_ble/const.py`**

Add `from habluetooth import BluetoothServiceInfoBleak` (habluetooth is a runtime dependency of the bluetooth component and already imported by `volcano_ble.py`) and:

```python
STORZ_BICKEL_MANUFACTURER_ID = 1736

# The Venty and Veazy advertise this one service (VENTY_BLE_SPEC.md §1).
QVAP_SERVICE_UUID = "00000000-5354-4f52-5a26-4249434b454c"
# The Crafty advertises its three services (CRAFTY_BLE_SPEC.md §1).
CRAFTY_SERVICE_UUIDS = (
    "00000001-4c45-4b43-4942-265a524f5453",
    "00000002-4c45-4b43-4942-265a524f5453",
    "00000003-4c45-4b43-4942-265a524f5453",
)
CRAFTY_NAME_PREFIXES = ("STORZ&BICKEL", "Storz&Bickel")


def detect_family(service_info: BluetoothServiceInfoBleak) -> DeviceFamily | None:
    """
    Decide which family an advertisement belongs to, or None.

    The order matters: the Volcano check is the one the integration has always
    made (name plus manufacturer id); the Venty/Veazy names are exact prefixes
    the vendor app matches on; a Qvap service with an unknown name is refused
    rather than guessed; the Crafty is last because its name is the least
    specific.
    """
    name = service_info.name or ""
    uuids = set(service_info.service_uuids)
    if (
        service_info.manufacturer_id == STORZ_BICKEL_MANUFACTURER_ID
        and "VOLCANO H" in name
    ):
        return DeviceFamily.VOLCANO_HYBRID
    if "S&B VY" in name:
        return DeviceFamily.VENTY
    if "S&B VZ" in name:
        return DeviceFamily.VEAZY
    if QVAP_SERVICE_UUID in uuids:
        return None
    if name.startswith(CRAFTY_NAME_PREFIXES) or uuids & set(CRAFTY_SERVICE_UUIDS):
        return DeviceFamily.CRAFTY
    return None


def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
    """Whether the advertisement belongs to a device this integration supports."""
    return detect_family(service_info) is not None
```

In `volcano_ble.py`, replace the body of `VolcanoBLE.is_supported` with `return is_supported(service_info)` and import it; delete the local `STORZ_BICKEL_MANUFACTURER_ID` and import it from `.const` instead (tests import it from `volcano_ble.volcano_ble`, so keep the name importable there).

- [ ] **Step 5: Run the tests**

Run: `RUN_TESTS tests/test_detect_family.py tests/test_volcano_ble.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests
git commit -m "Recognise the Crafty, Venty and Veazy from their advertisements"
```

---

### Task 3: `StorzBickelDevice` base, `VolcanoDevice`, `create_device`

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/device.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/volcano_ble.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/__init__.py`
- Test: `tests/test_volcano_ble.py` (must pass unchanged), `tests/test_device.py` (new)

**Interfaces:**
- Produces `class StorzBickelDevice(VolcanoHybridDataStatusProvider)` with `__init__(data_updated, device_updated, *, device=None)`, class attrs `family: DeviceFamily` and `data_class: type[DeviceData]`, attribute `data`, `is_connected`, `rssi`, `connected_addr`, `async_manual_update(device=None)`, `async_disconnect()`, `_ensure_client_connected()`, `_write_gatt(service_uuid, characteristic, value)`, `_async_read_and_subscribe(service_uuid, characteristic, callback, subscribe)`, `_async_read_optional(...)`, `_get_characteristic`, `_after_data_updated`, `_after_device_updated`; module function `_decode_ascii`. Hooks subclasses implement: `async _async_read_initial()`, `async _async_refresh()`, `async _async_try_ensure_written_values()`, `_on_disconnected()` (no-op by default). Default `async_set_*` methods raise `UnsupportedCommandError`.
- Produces `class UnsupportedCommandError(Exception)`.
- Produces `DATA_CLASSES: dict[DeviceFamily, type[DeviceData]]`, `DEVICE_CLASSES: dict[DeviceFamily, type[StorzBickelDevice]]`, `create_device(family, data_updated, device_updated) -> StorzBickelDevice` in `volcano_ble/families.py` (a separate module so it can import every device class at top level without a cycle). Tasks 6 and 9 add their families there.
- `VolcanoDevice(StorzBickelDevice)`; `VolcanoBLE = VolcanoDevice`.

- [ ] **Step 1: Write the failing test for the factory and the base contract**

Create `tests/test_device.py`:

```python
"""Tests for the device base class and factory."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble.const import DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.device import (
    StorzBickelDevice,
    UnsupportedCommandError,
)
from custom_components.volcano_hybrid.volcano_ble.families import (
    DATA_CLASSES,
    DEVICE_CLASSES,
    create_device,
)
from custom_components.volcano_hybrid.volcano_ble.volcano_ble import VolcanoDevice
from custom_components.volcano_hybrid.volcano_ble.volcano_hybrid_data import (
    VolcanoHybridData,
)


def test_factory_builds_the_volcano() -> None:
    """The Volcano family maps to today's device and data classes."""
    device = create_device(DeviceFamily.VOLCANO_HYBRID, lambda: None, lambda: None)
    assert isinstance(device, VolcanoDevice)
    assert isinstance(device, StorzBickelDevice)
    assert isinstance(device.data, VolcanoHybridData)
    assert device.family is DeviceFamily.VOLCANO_HYBRID
    assert DATA_CLASSES[DeviceFamily.VOLCANO_HYBRID] is VolcanoHybridData
    assert DEVICE_CLASSES[DeviceFamily.VOLCANO_HYBRID] is VolcanoDevice


def test_every_family_has_a_device_and_data_class() -> None:
    """A family without an implementation cannot be configured."""
    for family in DEVICE_CLASSES:
        assert DATA_CLASSES[family].family is family
        assert DEVICE_CLASSES[family].family is family


async def test_base_commands_are_unsupported() -> None:
    """A family that does not override a command refuses it, never sends it."""
    device = create_device(DeviceFamily.VOLCANO_HYBRID, lambda: None, lambda: None)
    with pytest.raises(UnsupportedCommandError):
        await StorzBickelDevice.async_set_boost_temperature(device, 10)
```

- [ ] **Step 2: Run to verify failure**

Run: `RUN_TESTS tests/test_device.py -q`
Expected: FAIL — `ModuleNotFoundError: ... volcano_ble.device`

- [ ] **Step 3: Create `volcano_ble/device.py` by moving the shared code out of `volcano_ble.py`**

Move these members of `VolcanoBLE` **verbatim** (docstrings and comments included) into the new base class: `__init__` (changed below), `rssi` property + setter, `connected_addr` property + setter, `is_connected`, `async_manual_update` (changed), `_ensure_client_connected`, `_async_connect` (changed), `_determine_connected_device`, `_disconnected` (changed), `_async_read_and_subscribe_all` (changed), `async_disconnect` (changed), `_get_characteristic`, `_async_read_optional`, `_async_read_and_subscribe`, `_write_gatt`, and the module-level `_decode_ascii`. The skeleton with the changes:

```python
"""The connection and GATT plumbing every Storz & Bickel device shares."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, ClassVar

from bleak import BleakClient, BleakError, BleakGATTCharacteristic, BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from .const import FAMILY_MODEL_NAME, DeviceFamily, is_supported
from .data import DeviceData, VolcanoHybridDataStatusProvider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from habluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)


class UnsupportedCommandError(Exception):
    """The device cannot carry out this command (family, firmware or mode)."""


class StorzBickelDevice(VolcanoHybridDataStatusProvider):
    """Connection handling shared by every family; subclasses speak the protocol."""

    family: ClassVar[DeviceFamily]
    data_class: ClassVar[type[DeviceData]]

    def __init__(
        self,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
        *,
        device: BLEDevice | None = None,
    ) -> None:
        """Initialize the device."""
        super().__init__()
        self._after_data_updated = data_updated
        self._after_device_updated = device_updated
        # (keep the connect-lock comment from VolcanoBLE.__init__ here)
        self._connect_lock = asyncio.Lock()
        self.client: BleakClient | None = None
        self.device = device
        self.data: DeviceData = self.data_class(self)
        self.device_rssi: int | None = None
        self.device_connected_addr: str | None = None

    @staticmethod
    def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if the device is supported."""
        return is_supported(service_info)

    # rssi / connected_addr / is_connected: moved verbatim

    async def async_manual_update(self, device: BLEDevice | None = None) -> DeviceData:
        """(docstring moved verbatim from VolcanoBLE)"""
        if device and device != self.device:
            await self.async_disconnect()
            self.device = device
            self._after_data_updated()

        await self._ensure_client_connected()
        await self._async_refresh()
        await self._async_try_ensure_written_values()
        return self.data

    # _ensure_client_connected, _async_connect: moved verbatim, except that the
    # literal "Volcano Hybrid" passed to establish_connection becomes
    # FAMILY_MODEL_NAME[self.family].

    async def _async_read_and_subscribe_all(self) -> DeviceData:
        """Read all required characteristics from the BLE device."""
        try:
            await self._async_read_initial()
        except BleakError:
            _LOGGER.exception("Error reading characteristics")
        return self.data

    def _disconnected(self, client: BleakClient) -> None:
        """Handle disconnection events."""
        _LOGGER.debug("Disconnected from BLE device at %s", client.address)
        self.client = None
        self._on_disconnected()
        self._after_data_updated()

    async def async_disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client:
            if self.client.is_connected:
                await self.client.disconnect()
            self.client = None
            self._on_disconnected()
            self._after_data_updated()

    # _get_characteristic, _async_read_optional, _async_read_and_subscribe,
    # _write_gatt: moved verbatim

    # -- hooks -----------------------------------------------------------

    async def _async_read_initial(self) -> None:
        """Read and subscribe to everything once, right after connecting."""
        raise NotImplementedError

    async def _async_refresh(self) -> None:
        """Re-read what a dropped notification would otherwise leave stale."""
        raise NotImplementedError

    async def _async_try_ensure_written_values(self) -> None:
        """Replay pending writes, dropping them when the device is off."""
        raise NotImplementedError

    def _on_disconnected(self) -> None:
        """Release anything tied to the connection (a poll task, for one)."""

    # -- commands: every family overrides the ones it can do -------------

    def _unsupported(self) -> UnsupportedCommandError:
        return UnsupportedCommandError(f"{self.family} cannot do this")

    async def async_set_heater(self, on: bool) -> bool:
        """Turn the heater on or off."""
        raise self._unsupported()

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the target temperature."""
        raise self._unsupported()

    async def async_set_fan(self, on: bool) -> bool:
        """Turn the pump on or off (Volcano)."""
        raise self._unsupported()

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Display in Celsius or Fahrenheit."""
        raise self._unsupported()

    async def async_set_display_on_cooling(self, on: bool) -> bool:
        """Keep the display on while cooling (Volcano)."""
        raise self._unsupported()

    async def async_set_vibration(self, on: bool) -> bool:
        """Enable or disable vibration."""
        raise self._unsupported()

    async def async_set_shut_off(self, minutes: int) -> bool:
        """Set the auto-off time in minutes (Volcano)."""
        raise self._unsupported()

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness (Volcano, Crafty)."""
        raise self._unsupported()

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset (Crafty, Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_superboost_temperature(self, offset: int) -> bool:
        """Set the superboost offset (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_auto_off_seconds(self, seconds: int) -> bool:
        """Set the auto-off time in seconds (Crafty)."""
        raise self._unsupported()

    async def async_set_charge_led(self, on: bool) -> bool:
        """Enable or disable the charge LED (Crafty)."""
        raise self._unsupported()

    async def async_set_auto_ble_shutdown(self, on: bool) -> bool:
        """Enable or disable automatic Bluetooth shutdown (Crafty)."""
        raise self._unsupported()

    async def async_find_device(self) -> bool:
        """Make the device signal so it can be found (Crafty+, Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_charge_optimization(self, on: bool) -> bool:
        """Enable or disable charge optimisation (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_charge_limit(self, on: bool) -> bool:
        """Enable or disable the charge limit (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_boost_visualization(self, on: bool) -> bool:
        """Show or hide boost on the display (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_boost_timeout_disabled(self, on: bool) -> bool:
        """Disable or enable the boost timeout (Venty, Veazy)."""
        raise self._unsupported()

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Keep Bluetooth on while asleep (Veazy)."""
        raise self._unsupported()

    async def async_set_brightness(self, brightness: int) -> bool:
        """Set the display brightness 1–9 (Venty, Veazy)."""
        raise self._unsupported()
```

- [ ] **Step 4: Reduce `volcano_ble.py` to `VolcanoDevice`**

- `class VolcanoDevice(StorzBickelDevice)` with `family = DeviceFamily.VOLCANO_HYBRID`, `data_class = VolcanoHybridData`, and a class-level annotation `data: VolcanoHybridData` so mypy narrows the type.
- Delete every member moved in Step 3, and `__init__` entirely.
- Rename `_async_read_initial_characteristics` → `_async_read_initial`.
- Add:

```python
    async def _async_refresh(self) -> None:
        # Re-read the current temperature rather than trusting the
        # subscription. (keep the rest of the comment that was in
        # async_manual_update)
        await self._async_read_current_temp()
```

- Keep `_async_try_ensure_written_values` and every `async_set_*` as they are.
- Last line of the module: `VolcanoBLE = VolcanoDevice` with a comment that the old name stays importable for one release.
- Imports: `from .const import STORZ_BICKEL_MANUFACTURER_ID, DeviceFamily` (the test module imports the id from here), `from .device import StorzBickelDevice, _decode_ascii`, `from .volcano_hybrid_data import VolcanoHybridData`.

- [ ] **Step 5: Create `volcano_ble/families.py` and update `__init__.py`**

```python
"""The registry of device families: which class speaks which protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DeviceFamily
from .volcano_ble import VolcanoDevice

if TYPE_CHECKING:
    from collections.abc import Callable

    from .data import DeviceData
    from .device import StorzBickelDevice

DEVICE_CLASSES: dict[DeviceFamily, type[StorzBickelDevice]] = {
    DeviceFamily.VOLCANO_HYBRID: VolcanoDevice,
}
DATA_CLASSES: dict[DeviceFamily, type[DeviceData]] = {
    family: cls.data_class for family, cls in DEVICE_CLASSES.items()
}


def create_device(
    family: DeviceFamily,
    data_updated: Callable[[], None],
    device_updated: Callable[[], None],
) -> StorzBickelDevice:
    """Build the device class that speaks the family's protocol."""
    return DEVICE_CLASSES[family](data_updated, device_updated)
```

`volcano_ble/__init__.py`:

```python
"""Volcano BLE module for communicating with the device."""

from .const import DeviceFamily, VolcanoSensor, detect_family, is_supported
from .data import DeviceData
from .device import StorzBickelDevice, UnsupportedCommandError
from .families import DATA_CLASSES, DEVICE_CLASSES, create_device
from .fault_log import FAULT_OPTIONS
from .volcano_ble import VolcanoBLE, VolcanoDevice
from .volcano_hybrid_data import VolcanoHybridData

__all__ = [
    "DATA_CLASSES",
    "DEVICE_CLASSES",
    "FAULT_OPTIONS",
    "DeviceData",
    "DeviceFamily",
    "StorzBickelDevice",
    "UnsupportedCommandError",
    "VolcanoBLE",
    "VolcanoDevice",
    "VolcanoHybridData",
    "VolcanoSensor",
    "create_device",
    "detect_family",
    "is_supported",
]
```

- [ ] **Step 6: Run the protocol tests**

Run: `RUN_TESTS tests/test_device.py tests/test_volcano_ble.py tests/test_volcano_hybrid_data.py -q`
Expected: PASS (`test_volcano_ble.py` still imports `VolcanoBLE` and `STORZ_BICKEL_MANUFACTURER_ID` from `volcano_ble.volcano_ble`; both resolve).

- [ ] **Step 7: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests/test_device.py
git commit -m "Split the shared BLE plumbing from the Volcano protocol"
```

---

### Task 4: Family-aware coordinator, config-entry model, migration, discovery matchers

**Files:**
- Modify: `custom_components/volcano_hybrid/const.py`, `coordinator.py`, `__init__.py`, `config_flow.py`, `manifest.json`, `strings.json`, `translations/en.json`
- Modify: `tests/__init__.py`, `tests/conftest.py`, `tests/test_config_flow.py`, `tests/test_init.py`, `tests/test_coordinator.py`

**Interfaces:**
- Consumes `create_device`, `detect_family`, `DeviceFamily`, `FAMILY_MODEL_NAME`, `UnsupportedCommandError`, `DeviceData.model_name`.
- Produces `CONF_MODEL = "model"`; `VolcanoHybridCoordinator(hass, config_entry, address, family)` with `.family`; `async_migrate_entry`; `ConfigFlow.VERSION = 2`; exception key `not_supported`.
- Produces test helpers: `FakeDevice(family=DeviceFamily.VOLCANO_HYBRID)` with `.attach(family, data_updated, device_updated)`; `FakeVolcanoBLE = FakeDevice`; `make_config_entry(family, address=VOLCANO_ADDRESS)`; fixtures `device_family` (default Volcano; override with `@pytest.mark.parametrize("device_family", [...], indirect=True)`) and `mock_volcano`, `init_integration` using it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_init.py`:

```python
async def test_migrate_v1_entry_marks_it_a_volcano(
    hass: HomeAssistant, mock_volcano: FakeVolcanoBLE, enable_bluetooth: None
) -> None:
    """Entries created before families existed are Volcano Hybrids."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=VOLCANO_ADDRESS,
        data={CONF_ADDRESS: VOLCANO_ADDRESS},
        title=VOLCANO_NAME,
        version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.data == {CONF_ADDRESS: VOLCANO_ADDRESS, CONF_MODEL: "volcano_hybrid"}
    assert entry.state is ConfigEntryState.LOADED
```

Append to `tests/test_config_flow.py`:

```python
@pytest.mark.parametrize(
    ("name", "manufacturer_id", "model"),
    [
        (VOLCANO_NAME, 1736, "volcano_hybrid"),
        (CRAFTY_NAME, 76, "crafty"),
        (VENTY_NAME, 76, "venty"),
        (VEAZY_NAME, 76, "veazy"),
    ],
)
async def test_bluetooth_flow_records_the_family(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    name: str,
    manufacturer_id: int,
    model: str,
) -> None:
    """Every family is discovered and its model is stored in the entry."""
    info = make_service_info(name=name, manufacturer_id=manufacturer_id)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == name
    assert result["data"] == {CONF_ADDRESS: VOLCANO_ADDRESS, CONF_MODEL: model}


async def test_bluetooth_flow_refuses_an_unknown_qvap_device(
    hass: HomeAssistant,
) -> None:
    """A Qvap service with an unknown name is not set up as a guess."""
    info = make_service_info(
        name="S&B XX000000", manufacturer_id=76, service_uuids=[QVAP_SERVICE_UUID]
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_user_flow_offers_every_family(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The dropdown lists a Crafty next to a Volcano and records its family."""
    crafty = make_service_info(
        address=OTHER_ADDRESS, name=CRAFTY_NAME, manufacturer_id=76
    )
    with _patch_discovered([make_service_info(), crafty]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: OTHER_ADDRESS}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == CRAFTY_NAME
    assert result["data"] == {CONF_ADDRESS: OTHER_ADDRESS, CONF_MODEL: "crafty"}
```

Add the imports (`pytest`, `CRAFTY_NAME`, `VENTY_NAME`, `VEAZY_NAME`, `CONF_MODEL`, `QVAP_SERVICE_UUID` from `volcano_ble.const`). Update every existing assertion `result["data"] == {CONF_ADDRESS: X}` to `{CONF_ADDRESS: X, CONF_MODEL: "volcano_hybrid"}`; `_volcano_entry()` gains `CONF_MODEL: "volcano_hybrid"` and `version=2`.

- [ ] **Step 2: Run to verify failure**

Run: `RUN_TESTS tests/test_init.py tests/test_config_flow.py -q`
Expected: FAIL — `ImportError: cannot import name 'CONF_MODEL'`

- [ ] **Step 3: `const.py` and the coordinator**

`const.py`: add `CONF_MODEL = "model"` and list it in `__all__`.

`coordinator.py`:
- Imports: replace `from .volcano_ble import VolcanoBLE, VolcanoHybridData` with `from .volcano_ble import DeviceData, DeviceFamily, StorzBickelDevice, UnsupportedCommandError, create_device` and `from .volcano_ble.const import FAMILY_MODEL_NAME`.
- Delete `DEFAULT_MODEL` and `_model_name` (they moved to `VolcanoHybridData.model_name` in Task 1).
- `class VolcanoHybridCoordinator(DataUpdateCoordinator[DeviceData])`; `__init__(self, hass, config_entry, address, family: DeviceFamily)`:

```python
        self.family = family
        model = FAMILY_MODEL_NAME[family]
        super().__init__(
            hass,
            _LOGGER,
            name=model,
            config_entry=config_entry,
            update_interval=timedelta(seconds=10),
            always_update=True,
        )
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=model,
            manufacturer="Storz & Bickel",
            model=model,
            connections={(CONNECTION_BLUETOOTH, address)},
        )
        self._device: StorzBickelDevice = create_device(
            family, self.async_update_listeners, self.update_device
        )
```

- `async_update_listeners`: the two `_LOGGER.info` lines use `self.name` in place of "Volcano Hybrid".
- `update_device`: `model = self.data.model_name`, comments kept.
- `_async_command`:

```python
        try:
            written = await command
        except UnsupportedCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_supported",
            ) from err
        except BleakError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
            ) from err
        if not written:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
            )
```

- The existing `set_*` methods stay unchanged; the base class stubs from Task 3 make them type-check for every family.

- [ ] **Step 4: `__init__.py` — pass the family, migrate v1 entries**

```python
from .const import CONF_MODEL, DOMAIN
from .volcano_ble import DeviceFamily


async def async_setup_entry(hass: HomeAssistant, entry: VolcanoHybridConfigEntry) -> bool:
    """Set up a Storz & Bickel device from a config entry."""
    coordinator = VolcanoHybridCoordinator(
        hass,
        config_entry=entry,
        address=entry.data[CONF_ADDRESS],
        family=DeviceFamily(entry.data[CONF_MODEL]),
    )
    # ... the rest exactly as today


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Migrate old entries.

    Version 1 entries predate family support and were only ever Volcano Hybrids.
    """
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_MODEL: DeviceFamily.VOLCANO_HYBRID.value},
            version=2,
        )
    return True
```

- [ ] **Step 5: `config_flow.py`**

- `VERSION = 2`.
- `self._discovered_devices: dict[str, tuple[str, DeviceFamily]]`; `self._discovered_family: DeviceFamily | None = None`.
- `_async_discover_devices`: replace `if VolcanoBLE.is_supported(discovery_info):` with `if (family := detect_family(discovery_info)) is not None:` and store `(discovery_info.name, family)`.
- `_device_selection_schema`: label from `name` (`for address, (name, _) in ...`).
- Add:

```python
    def _entry_data(self, address: str) -> dict[str, str]:
        """The data a new or reconfigured entry stores for a discovered device."""
        _, family = self._discovered_devices[address]
        return {CONF_ADDRESS: address, CONF_MODEL: family.value}
```

- `async_step_user`: `title=self._discovered_devices[address][0]`, `data=self._entry_data(address)`. `async_step_reconfigure`: same via `async_update_reload_and_abort(entry, unique_id=address, title=..., data=self._entry_data(address))`.
- `async_step_bluetooth`: `family = detect_family(discovery_info)`; `if family is None: return self.async_abort(reason="not_supported")`; `self._discovered_family = family`.
- `async_step_bluetooth_confirm`: `if self._discovered_device is None or self._discovered_family is None: abort no_devices_found`; create entry with `data={CONF_ADDRESS: self._discovered_device.address, CONF_MODEL: self._discovered_family.value}`.
- Replace the `VolcanoBLE` import with `from .volcano_ble import DeviceFamily, detect_family` and add `CONF_MODEL` to the const import.

- [ ] **Step 6: Manifest and strings**

`manifest.json`: `"name": "Storz & Bickel"` and

```json
  "bluetooth": [
    { "manufacturer_id": 1736, "local_name": "S&B VOLCANO*" },
    { "local_name": "S&B VY*" },
    { "local_name": "S&B VZ*" },
    { "service_uuid": "00000000-5354-4f52-5a26-4249434b454c" },
    { "local_name": "STORZ&BICKEL*" },
    { "local_name": "Storz&Bickel*" },
    { "service_uuid": "00000001-4c45-4b43-4942-265a524f5453" }
  ],
```

`strings.json` and `translations/en.json`: under `exceptions` add

```json
    "not_supported": {
      "message": "The device cannot carry out this command with its family, firmware version or current mode"
    }
```

change the two existing messages to "…the device is not connected" / "Sending the command to the device failed"; `config.step.user.data_description.address` → "The device to set up"; reconfigure → "The device to use".

- [ ] **Step 7: Test fakes and fixtures**

`tests/__init__.py`:

```python
from custom_components.volcano_hybrid.const import CONF_MODEL, DOMAIN
from custom_components.volcano_hybrid.volcano_ble import DATA_CLASSES, DeviceFamily
from custom_components.volcano_hybrid.volcano_ble.volcano_hybrid_data import (
    VolcanoHybridDataStatusProvider,
)

CRAFTY_NAME = "STORZ&BICKEL"
VENTY_NAME = "S&B VY123456"
VEAZY_NAME = "S&B VZ654321"
FAMILY_NAMES: dict[DeviceFamily, str] = {
    DeviceFamily.VOLCANO_HYBRID: VOLCANO_NAME,
    DeviceFamily.CRAFTY: CRAFTY_NAME,
    DeviceFamily.VENTY: VENTY_NAME,
    DeviceFamily.VEAZY: VEAZY_NAME,
}


def make_config_entry(
    family: DeviceFamily = DeviceFamily.VOLCANO_HYBRID,
    address: str = VOLCANO_ADDRESS,
) -> MockConfigEntry:
    """Build a configured entry for a device of the given family."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=address,
        data={CONF_ADDRESS: address, CONF_MODEL: family.value},
        title=FAMILY_NAMES[family],
        version=2,
    )


class FakeDevice(VolcanoHybridDataStatusProvider):
    """In-memory stand-in for a device, used by the coordinator tests."""

    def __init__(self, family: DeviceFamily = DeviceFamily.VOLCANO_HYBRID) -> None:
        """Initialize the fake device."""
        self.family = family
        self.data: Any = DATA_CLASSES[family](self)
        # ... every other attribute exactly as FakeVolcanoBLE had them

    def attach(
        self,
        family: DeviceFamily,
        data_updated: Callable[[], None],
        device_updated: Callable[[], None],
    ) -> FakeDevice:
        """Stand in for create_device()."""
        assert family is self.family
        self.data_updated = data_updated
        self.device_updated = device_updated
        return self

    # async_manual_update, async_disconnect, _command and the existing
    # async_set_* methods stay as they are.


FakeVolcanoBLE = FakeDevice
```

`tests/conftest.py`:

```python
@pytest.fixture
def device_family(request: pytest.FixtureRequest) -> DeviceFamily:
    """The family the fake speaks; parametrize indirectly to test another."""
    return getattr(request, "param", DeviceFamily.VOLCANO_HYBRID)


@pytest.fixture
def mock_volcano(device_family: DeviceFamily) -> Generator[FakeDevice]:
    """Replace the protocol layer with an in-memory fake."""
    fake = FakeDevice(device_family)
    with patch(
        "custom_components.volcano_hybrid.coordinator.create_device",
        side_effect=fake.attach,
    ):
        yield fake


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_volcano: FakeDevice,
    enable_bluetooth: None,
    device_family: DeviceFamily,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration with a mocked device."""
    entry = make_config_entry(device_family)
    entry.add_to_hass(hass)
    # ... setup and teardown unchanged
```

In `tests/test_init.py` and `tests/test_coordinator.py`, every `MockConfigEntry(... data={CONF_ADDRESS: ...})` that gets *loaded* becomes `make_config_entry()` (or gains `CONF_MODEL: "volcano_hybrid"` and `version=2`); direct `VolcanoHybridCoordinator(hass, entry, address)` calls gain `family=DeviceFamily.VOLCANO_HYBRID`.

- [ ] **Step 8: Run the whole suite**

Run: `RUN_TESTS`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A custom_components tests
git commit -m "Store the device family in the config entry and build the device from it"
```

---

### Task 5: Capability-filtered platforms and the golden entity list

**Files:**
- Modify: `custom_components/volcano_hybrid/climate.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `button.py`, `update.py`
- Test: `tests/test_entities_by_family.py` (new)

**Interfaces:**
- Consumes `coordinator.data.capabilities`, `DeviceData.MIN_DISPLAY_TEMP` / `MAX_TEMP`, `VolcanoSensor.PUMP_ACTIVE` (presence means "has a fan").
- Produces, in every platform, a module-level ordered tuple of the keys it can create (with per-key flags) and an `async_setup_entry` that keeps only keys in `capabilities`. Later tasks only append rows to the description tables and key tuples.
- Produces `GOLDEN_ENTITIES: dict[DeviceFamily, dict[str, set[str]]]` in the new test — the authoritative entity list per family, extended in Tasks 8 and 11.

- [ ] **Step 1: Write the failing golden test**

Create `tests/test_entities_by_family.py`:

```python
"""One test per family pinning the exact entity set it creates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_hybrid.const import DOMAIN
from custom_components.volcano_hybrid.volcano_ble import DeviceFamily

from . import VOLCANO_ADDRESS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

# Platform -> keys. A key here is `{address}-{key}`'s key part. Extend the
# family's block when a task adds an entity; a leak from another family fails.
GOLDEN_ENTITIES: dict[DeviceFamily, dict[str, set[str]]] = {
    DeviceFamily.VOLCANO_HYBRID: {
        "climate": {"volcano"},
        "number": {"shut_off", "led_brightness"},
        "switch": {"showing_celsius", "display_on_cooling", "vibration", "auto_connect"},
        "sensor": {
            "current_auto_off_time", "current_on_time", "heat_time", "rssi",
            "connected_addr", "mains_voltage", "prj1", "prj2", "prj3", "prj4",
            "prj5", "hist1", "hist2", "last_fault",
        },
        "binary_sensor": {
            "at_temperature", "heater", "fan", "actuator_fault", "auto_shutdown",
            "service_mode", "prv1_error", "prv2_error", "connected",
        },
        "button": {"reconnect", "delayed_reconnect"},
        "update": {"firmware"},
    },
}


@pytest.mark.parametrize(
    "device_family", list(GOLDEN_ENTITIES), indirect=True, ids=str
)
async def test_entity_set_per_family(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    device_family: DeviceFamily,
) -> None:
    """Exactly the golden entities exist for the family, no more, no fewer."""
    registry = er.async_get(hass)
    created: dict[str, set[str]] = {}
    for entry in er.async_entries_for_config_entry(registry, init_integration.entry_id):
        assert entry.unique_id.startswith(f"{VOLCANO_ADDRESS}-")
        created.setdefault(entry.domain, set()).add(
            entry.unique_id.removeprefix(f"{VOLCANO_ADDRESS}-")
        )
    assert created == GOLDEN_ENTITIES[device_family]
```

- [ ] **Step 2: Run it**

Run: `RUN_TESTS tests/test_entities_by_family.py -q`
Expected: PASS already for the Volcano (nothing filtered yet). That is the point: the test pins today's set before the filtering lands. If it fails, the golden block is wrong — fix the block, not the code.

- [ ] **Step 3: Filter every platform by capability**

`sensor.py` — replace the hand-written list in `async_setup_entry`:

```python
# (key, always_available) in the order the entities were always created.
SENSOR_KEYS: tuple[tuple[VolcanoSensor, bool], ...] = (
    (VolcanoSensor.CURRENT_AUTO_OFF_TIME, False),
    (VolcanoSensor.CURRENT_ON_TIME, False),
    (VolcanoSensor.HEAT_TIME, False),
    (VolcanoSensor.RSSI, True),
    (VolcanoSensor.CONNECTED_ADDR, True),
    (VolcanoSensor.MAINS_VOLTAGE, False),
    (VolcanoSensor.PRJ1, False),
    (VolcanoSensor.PRJ2, False),
    (VolcanoSensor.PRJ3, False),
    (VolcanoSensor.PRJ4, False),
    (VolcanoSensor.PRJ5, False),
    (VolcanoSensor.HIST1, False),
    (VolcanoSensor.HIST2, False),
    (VolcanoSensor.LAST_FAULT, False),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the sensors the device family supports."""
    coordinator = entry.runtime_data
    capabilities = coordinator.data.capabilities
    async_add_entities(
        VolcanoSensorEntity(coordinator, key, always_available=always_available)
        for key, always_available in SENSOR_KEYS
        if key in capabilities
    )
```

`binary_sensor.py` — `BINARY_SENSOR_KEYS: tuple[tuple[VolcanoSensor, bool, bool | None], ...]` of `(key, always_available, initial_value)`; the `CONNECTED` row is `(VolcanoSensor.CONNECTED, True, False)`, all others `(key, False, None)`. Same filter.

`switch.py` — `SWITCH_KEYS = (SHOWING_CELSIUS, DISPLAY_ON_COOLING, VIBRATION)` filtered, then `VolcanoAutoConnectSwitch` appended when `VolcanoSensor.AUTO_CONNECT in capabilities`.

`number.py` — `NUMBER_KEYS = (SHUT_OFF, LED_BRIGHTNESS)` filtered.

`button.py` — build `[(RECONNECT, _async_reconnect), (DELAYED_RECONNECT, _async_delayed_reconnect)]` and filter.

`update.py` — `if VolcanoSensor.FIRMWARE in coordinator.data.capabilities: async_add_entities([...])`.

`climate.py` — created when `VolcanoSensor.VOLCANO in capabilities`. Replace the class attributes `_attr_min_temp`, `_attr_max_temp`, `_attr_fan_modes`, `_attr_supported_features` with instance attributes set in `__init__`:

```python
        data = coordinator.data
        self._attr_min_temp = data.MIN_DISPLAY_TEMP
        self._attr_max_temp = data.MAX_TEMP
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        # Only the Volcano has a pump; the portable devices have no fan mode.
        self._has_fan = VolcanoSensor.PUMP_ACTIVE in data.capabilities
        if self._has_fan:
            features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = [FAN_OFF, FAN_ON]
        self._attr_supported_features = features
```

and in `_update_attrs`, guard the fan block with `if self._has_fan:` and read `data.get("fan_state")` instead of `data.fan_state` (the base data has no fan). `VOLCANO_HYBRID_MIN_DISPLAY_TEMP` / `VOLCANO_HYBRID_MAX_TEMP` imports go; the const module keeps exporting them for anyone else.

- [ ] **Step 4: Run the suite**

Run: `RUN_TESTS`
Expected: PASS — the Volcano's set is unchanged, so the golden test and every platform test still pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/volcano_hybrid tests/test_entities_by_family.py
git commit -m "Create only the entities a device family declares"
```

---

### Task 6: Crafty data model and decoders

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/crafty_data.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/const.py` (new keys)
- Test: `tests/test_crafty_data.py` (new)

**Interfaces:**
- Produces `VolcanoSensor` keys: `BATTERY = "battery"`, `BOOST_TEMP = "boost_temp"`, `BOOST_MODE = "boost_mode"`, `SUPERBOOST_MODE = "superboost_mode"`, `AUTO_OFF_SECONDS = "auto_off_seconds"`, `AUTO_OFF_COUNTDOWN = "auto_off_countdown"`, `CHARGE_LED = "charge_led"`, `AUTO_BLE_SHUTDOWN = "auto_ble_shutdown"`, `FIND_DEVICE = "find_device"`, `FIND_MODE = "find_mode"`, `ERROR = "error"`, `NEEDS_FACTORY_RESET = "needs_factory_reset"`, `SYSTEM_STATUS = "system_status"`, `BATTERY_STATUS1 = "battery_status1"`, `BATTERY_STATUS2 = "battery_status2"`.
- Produces `CraftyData(DeviceData)` with fields `battery`, `boost_temp`, `boost_mode`, `superboost_mode`, `led_brightness`, `auto_off_seconds`, `auto_off_countdown`, `heat_hours`, `heat_minutes`, `vibration`, `charge_led`, `auto_ble_shutdown`, `find_mode`, `prj1`, `prj2`, `system_status`, `battery_status1`, `battery_status2`, `error`, `needs_factory_reset`; properties `heat_time`, `firmware_generation`, `is_plus`, `is_old_firmware`, `model_name`; methods `apply_prj1(word)`, `apply_prj2(word)`, `apply_status_words()`.
- Produces pure functions `decode_target(raw: int) -> int`, `parse_crafty_firmware(version: str) -> tuple[int, int] | None`; mask constants `MASK_PRJSTAT_CRAFTY_ACTIVE = 0x0010`, `MASK_PRJSTAT_BOOST_MODE_ENABLED = 0x0020`, `MASK_PRJSTAT_SUPERBOOST_MODE_ENABLED = 0x0040`, `MASK_PRJSTAT_ERROR = 0x2008`, `MASK_PRJSTAT_NEEDS_FACTORY_RESET = 0x8000`, `MASK_PRJSTAT2_DISABLE_VIBRATION = 0x0001`, `MASK_PRJSTAT2_DISABLE_CHARGELED = 0x0002`, `MASK_PRJSTAT2_SET_TEMP_REACHED = 0x0004`, `MASK_PRJSTAT2_FIND_DEVICE = 0x0008`, `MASK_PRJSTAT2_ENABLE_AUTOBLESHUTDOWN = 0x1000`, `MASK_SYSTEM_ERROR = 0x0280`, `MASK_BATTERY1_ERROR = 0x0600`, `CRAFTY_SETTINGS_FIRMWARE = (2, 51)`, `CRAFTY_PLUS_MAJOR = 3`.

- [ ] **Step 1: Add the keys to `VolcanoSensor`**

Append the fifteen members listed above to `VolcanoSensor` in `volcano_ble/const.py`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_crafty_data.py`:

```python
"""Tests for decoding what a Crafty reports (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble.const import DeviceFamily, VolcanoSensor
from custom_components.volcano_hybrid.volcano_ble.crafty_data import (
    MASK_PRJSTAT2_SET_TEMP_REACHED,
    MASK_PRJSTAT_BOOST_MODE_ENABLED,
    MASK_PRJSTAT_CRAFTY_ACTIVE,
    CraftyData,
    decode_target,
    parse_crafty_firmware,
)

from . import FakeDevice


def _data() -> CraftyData:
    return FakeDevice(DeviceFamily.CRAFTY).data


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1850, 185),  # °C ×10
        (2100, 210),  # the top of the range is still Celsius
        (3650, 185),  # 365.0 °F: the device reports °F ×10 when set to °F (§3.1)
    ],
)
def test_decode_target(raw: int, expected: int) -> None:
    """A target over 210 is Fahrenheit and is converted."""
    assert decode_target(raw) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [("V02.51", (2, 51)), ("V03.02", (3, 2)), ("V02.49", (2, 49)), ("junk", None)],
)
def test_parse_crafty_firmware(version: str, expected: tuple[int, int] | None) -> None:
    """Major is characters 1-2, minor the last two, as the vendor app reads it."""
    assert parse_crafty_firmware(version) == expected


def test_firmware_generation_decides_the_model() -> None:
    """Crafty+ is major >= 3; below V02.51 the settings side is missing (§6)."""
    data = _data()
    assert data.model_name == "Crafty"
    assert data.is_plus is None
    data.firmware_version = "V02.49"
    assert data.is_old_firmware is True
    assert data.is_plus is False
    data.firmware_version = "V03.02"
    assert data.is_old_firmware is False
    assert data.is_plus is True
    assert data.model_name == "Crafty+"


def test_prj1_drives_heater_and_boost_flags() -> None:
    """PRJSTAT1 bit 4 is the heater, bits 5/6 the boost modes (§4.1)."""
    data = _data()
    data.apply_prj1(MASK_PRJSTAT_CRAFTY_ACTIVE | MASK_PRJSTAT_BOOST_MODE_ENABLED)
    assert data.heater is True
    assert data.boost_mode is True
    assert data.superboost_mode is False
    assert data.error is False
    assert data.needs_factory_reset is False
    assert data.prj1 == 0x0030

    data.apply_prj1(0x8008)
    assert data.heater is False
    assert data.error is True
    assert data.needs_factory_reset is True


def test_prj2_polarity() -> None:
    """The vibration and charge-LED bits are 'disabled' bits (§4.2)."""
    data = _data()
    data.apply_prj2(0x0003 | MASK_PRJSTAT2_SET_TEMP_REACHED)
    assert data.vibration is False
    assert data.charge_led is False
    assert data.at_temperature is True
    assert data.find_mode is False
    assert data.auto_ble_shutdown is False

    data.apply_prj2(0x1008)
    assert data.vibration is True
    assert data.charge_led is True
    assert data.find_mode is True
    assert data.auto_ble_shutdown is True


def test_status_words_raise_error() -> None:
    """The battery/system words flag the same 'contact support' masks the app tests."""
    data = _data()
    data.prj1 = 0
    data.system_status = 0x0200
    data.apply_status_words()
    assert data.error is True
    data.system_status = 0
    data.battery_status1 = 0x0400
    data.apply_status_words()
    assert data.error is True
    data.battery_status1 = 0x0003  # "please charge": not an error
    data.apply_status_words()
    assert data.error is False


def test_heat_time_and_capabilities() -> None:
    """Lifetime minutes combine hours and minutes; the family owns its keys."""
    data = _data()
    assert data.heat_time is None
    data.heat_hours = 2
    data.heat_minutes = 30
    assert data.heat_time == 150
    assert VolcanoSensor.BATTERY in data.capabilities
    assert VolcanoSensor.PUMP_ACTIVE not in data.capabilities
    assert data.MAX_TEMP == 210
```

- [ ] **Step 3: Run to verify failure**

Run: `RUN_TESTS tests/test_crafty_data.py -q`
Expected: FAIL — `ModuleNotFoundError: ... crafty_data`

- [ ] **Step 4: Create `volcano_ble/crafty_data.py`**

```python
"""State of a Crafty / Crafty+, and the pure decoders for it (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import re

from .const import (
    PORTABLE_MAX_TEMP,
    PORTABLE_MIN_DISPLAY_TEMP,
    PORTABLE_MIN_TEMP,
    DeviceFamily,
    VolcanoSensor,
)
from .data import DeviceData, VolcanoHybridDataStatusProvider

# PRJSTAT1 (spec §4.1)
MASK_PRJSTAT_CRAFTY_ACTIVE = 0x0010
MASK_PRJSTAT_BOOST_MODE_ENABLED = 0x0020
MASK_PRJSTAT_SUPERBOOST_MODE_ENABLED = 0x0040
MASK_PRJSTAT_ERROR = 0x2008
MASK_PRJSTAT_NEEDS_FACTORY_RESET = 0x8000
# PRJSTAT2 (spec §4.2) — bits 0 and 1 are *disable* bits
MASK_PRJSTAT2_DISABLE_VIBRATION = 0x0001
MASK_PRJSTAT2_DISABLE_CHARGELED = 0x0002
MASK_PRJSTAT2_SET_TEMP_REACHED = 0x0004
MASK_PRJSTAT2_FIND_DEVICE = 0x0008
MASK_PRJSTAT2_ENABLE_AUTOBLESHUTDOWN = 0x1000
# System / battery status words (spec §4.3): the "contact support" masks
MASK_SYSTEM_ERROR = 0x0280
MASK_BATTERY1_ERROR = 0x0600

# Firmware generations (spec §6)
CRAFTY_SETTINGS_FIRMWARE = (2, 51)
CRAFTY_PLUS_MAJOR = 3
# The app reads a °C target as anything up to the 210 °C maximum; above that
# the device is set to °F and reports °F ×10 over the same characteristic.
CRAFTY_MAX_CELSIUS = 210

_FIRMWARE = re.compile(r"^V?(\d{2})\.(\d{2})")


def decode_target(raw: int) -> int:
    """Turn a target reading (×10) into whole °C, converting a °F reading."""
    target = round(raw / 10)
    if target > CRAFTY_MAX_CELSIUS:
        return round((target - 32) / 1.8)
    return target


def parse_crafty_firmware(version: str | None) -> tuple[int, int] | None:
    """Major/minor out of the `V02.51`-style string the Crafty serves."""
    if version is None or (match := _FIRMWARE.match(version)) is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


class CraftyData(DeviceData):
    """Data object for a Crafty or Crafty+."""

    family = DeviceFamily.CRAFTY
    MIN_TEMP = PORTABLE_MIN_TEMP
    MAX_TEMP = PORTABLE_MAX_TEMP
    MIN_DISPLAY_TEMP = PORTABLE_MIN_DISPLAY_TEMP
    capabilities = frozenset(
        {
            VolcanoSensor.VOLCANO,
            VolcanoSensor.BOOST_TEMP, VolcanoSensor.LED_BRIGHTNESS,
            VolcanoSensor.AUTO_OFF_SECONDS,
            VolcanoSensor.VIBRATION, VolcanoSensor.CHARGE_LED,
            VolcanoSensor.AUTO_BLE_SHUTDOWN, VolcanoSensor.AUTO_CONNECT,
            VolcanoSensor.BATTERY, VolcanoSensor.AUTO_OFF_COUNTDOWN,
            VolcanoSensor.HEAT_TIME, VolcanoSensor.RSSI, VolcanoSensor.CONNECTED_ADDR,
            VolcanoSensor.PRJ1, VolcanoSensor.PRJ2, VolcanoSensor.SYSTEM_STATUS,
            VolcanoSensor.BATTERY_STATUS1, VolcanoSensor.BATTERY_STATUS2,
            VolcanoSensor.AT_TEMPERATURE, VolcanoSensor.HEATER_ACTIVE,
            VolcanoSensor.BOOST_MODE, VolcanoSensor.SUPERBOOST_MODE,
            VolcanoSensor.ERROR, VolcanoSensor.NEEDS_FACTORY_RESET,
            VolcanoSensor.FIND_MODE, VolcanoSensor.CONNECTED,
            VolcanoSensor.RECONNECT, VolcanoSensor.DELAYED_RECONNECT,
            VolcanoSensor.FIND_DEVICE,
        }
    )

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the Crafty fields."""
        super().__init__(device)
        self.battery: int | None = None
        self.boost_temp: int | None = None
        self.boost_mode: bool | None = None
        self.superboost_mode: bool | None = None
        self.led_brightness: int | None = None
        self.auto_off_seconds: int | None = None
        self.auto_off_countdown: int | None = None
        self.heat_hours: int | None = None
        self.heat_minutes: int | None = None
        self.vibration: bool | None = None
        self.charge_led: bool | None = None
        self.auto_ble_shutdown: bool | None = None
        self.find_mode: bool | None = None
        # Raw words, kept for diagnostics like the Volcano's registers.
        self.prj1: int | None = None
        self.prj2: int | None = None
        self.system_status: int | None = None
        self.battery_status1: int | None = None
        self.battery_status2: int | None = None
        self.error: bool | None = None
        self.needs_factory_reset: bool | None = None

    @property
    def firmware_generation(self) -> tuple[int, int] | None:
        """Major/minor of the reported firmware, if it has been read."""
        return parse_crafty_firmware(self.firmware_version)

    @property
    def is_plus(self) -> bool | None:
        """Whether this is a Crafty+ (firmware major >= 3), None until known."""
        generation = self.firmware_generation
        return None if generation is None else generation[0] >= CRAFTY_PLUS_MAJOR

    @property
    def is_old_firmware(self) -> bool | None:
        """Whether the settings characteristics are missing (< V02.51)."""
        generation = self.firmware_generation
        return None if generation is None else generation < CRAFTY_SETTINGS_FIRMWARE

    @property
    def model_name(self) -> str:
        """Crafty until the firmware says it is a Crafty+."""
        return "Crafty+" if self.is_plus else "Crafty"

    @property
    def heat_time(self) -> int | None:
        """Lifetime heating time in minutes."""
        if self.heat_hours is None:
            return None
        return self.heat_hours * 60 + (self.heat_minutes or 0)

    def apply_prj1(self, word: int) -> None:
        """Decode PRJSTAT1 (spec §4.1)."""
        self.prj1 = word
        self.heater = bool(word & MASK_PRJSTAT_CRAFTY_ACTIVE)
        self.boost_mode = bool(word & MASK_PRJSTAT_BOOST_MODE_ENABLED)
        self.superboost_mode = bool(word & MASK_PRJSTAT_SUPERBOOST_MODE_ENABLED)
        self.needs_factory_reset = bool(word & MASK_PRJSTAT_NEEDS_FACTORY_RESET)
        self.apply_status_words()

    def apply_prj2(self, word: int) -> None:
        """Decode PRJSTAT2 (spec §4.2)."""
        self.prj2 = word
        self.vibration = not word & MASK_PRJSTAT2_DISABLE_VIBRATION
        self.charge_led = not word & MASK_PRJSTAT2_DISABLE_CHARGELED
        self.at_temperature = bool(word & MASK_PRJSTAT2_SET_TEMP_REACHED)
        self.find_mode = bool(word & MASK_PRJSTAT2_FIND_DEVICE)
        self.auto_ble_shutdown = bool(word & MASK_PRJSTAT2_ENABLE_AUTOBLESHUTDOWN)

    def apply_status_words(self) -> None:
        """Combine the 'contact support' masks the vendor app tests (spec §4.3)."""
        self.error = bool(
            (self.prj1 or 0) & MASK_PRJSTAT_ERROR
            or (self.system_status or 0) & MASK_SYSTEM_ERROR
            or (self.battery_status1 or 0) & MASK_BATTERY1_ERROR
        )
```

- [ ] **Step 5: Register the data class so `FakeDevice(DeviceFamily.CRAFTY)` works**

In `volcano_ble/families.py` add `DeviceFamily.CRAFTY: CraftyData` to `DATA_CLASSES` explicitly for now (Task 7 replaces it with the device class's `data_class`): change the dict comprehension to a literal that lists the Volcano from `VolcanoDevice.data_class` and `CraftyData` directly.

- [ ] **Step 6: Run the tests**

Run: `RUN_TESTS tests/test_crafty_data.py tests/test_device.py -q`
Expected: PASS (`test_every_family_has_a_device_and_data_class` iterates `DEVICE_CLASSES`, which still has only the Volcano).

- [ ] **Step 7: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests/test_crafty_data.py
git commit -m "Decode what a Crafty reports"
```

---

### Task 7: `CraftyDevice`

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/crafty.py`
- Modify: `custom_components/volcano_hybrid/volcano_ble/families.py`
- Test: `tests/test_crafty_ble.py` (new); reuse `FakeBleakClient`, `FakeCharacteristic` from `tests/test_volcano_ble.py` by moving them into `tests/fakes.py`

**Interfaces:**
- Consumes `StorzBickelDevice`, `CraftyData`, the masks from Task 6.
- Produces `CraftyDevice(StorzBickelDevice)` with `family = DeviceFamily.CRAFTY`, `data_class = CraftyData`, UUID constants (below), and commands `async_set_heater`, `async_set_target_temperature`, `async_set_boost_temperature`, `async_set_led_brightness`, `async_set_auto_off_seconds`, `async_set_vibration`, `async_set_charge_led`, `async_set_auto_ble_shutdown`, `async_find_device`.
- Produces `tests/fakes.py` with `FakeCharacteristic`, `FakeService`, `FakeServices`, `FakeBleakClient` (moved verbatim; `test_volcano_ble.py` imports them from there).

- [ ] **Step 1: Move the bleak fakes**

Cut `FakeCharacteristic`, `FakeService`, `FakeServices`, `FakeBleakClient` from `tests/test_volcano_ble.py` into a new `tests/fakes.py` (module docstring `"""Fakes of the bleak client shared by the protocol-layer tests."""`), and import them back into `test_volcano_ble.py`. Give `FakeBleakClient.__init__` an `address: str = VOLCANO_ADDRESS` parameter. Run `RUN_TESTS tests/test_volcano_ble.py -q` → PASS.

- [ ] **Step 2: Write the failing protocol tests**

Create `tests/test_crafty_ble.py`:

```python
"""Tests for the Crafty protocol against a fake GATT server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.volcano_hybrid.volcano_ble.crafty import (
    CHAR_AUTO_OFF_COUNTDOWN,
    CHAR_AUTO_OFF_SETTING,
    CHAR_BATTERY,
    CHAR_BATTERY_STATUS1,
    CHAR_BATTERY_STATUS2,
    CHAR_BLE_FIRMWARE,
    CHAR_BOOST_TEMP,
    CHAR_CURRENT_TEMP,
    CHAR_FACTORY_RESET,
    CHAR_FIRMWARE,
    CHAR_HEATER_OFF,
    CHAR_HEATER_ON,
    CHAR_LED_BRIGHTNESS,
    CHAR_PRJSTAT1,
    CHAR_PRJSTAT2,
    CHAR_SECURITY_CODE,
    CHAR_SERIAL,
    CHAR_SYSTEM_STATUS,
    CHAR_TARGET_TEMP,
    CHAR_USE_HOURS,
    CHAR_USE_MINUTES,
    SECURITY_CODE_AUTO_OFF,
    CraftyDevice,
)
from custom_components.volcano_hybrid.volcano_ble.crafty_data import (
    MASK_PRJSTAT2_SET_TEMP_REACHED,
    MASK_PRJSTAT_CRAFTY_ACTIVE,
)
from custom_components.volcano_hybrid.volcano_ble.device import UnsupportedCommandError

from . import make_ble_device
from .fakes import FakeBleakClient

ESTABLISH = "custom_components.volcano_hybrid.volcano_ble.device.establish_connection"

# Characteristics only served from firmware V02.51 on (spec §3, §4, §5.1).
SETTINGS_CHARS = {
    CHAR_AUTO_OFF_SETTING, CHAR_AUTO_OFF_COUNTDOWN, CHAR_HEATER_ON, CHAR_HEATER_OFF,
    CHAR_USE_MINUTES, CHAR_BLE_FIRMWARE, CHAR_SECURITY_CODE, CHAR_FACTORY_RESET,
    CHAR_SYSTEM_STATUS, CHAR_BATTERY_STATUS1, CHAR_BATTERY_STATUS2,
}


def u16(value: int) -> bytes:
    return value.to_bytes(2, "little")


def crafty_plus_values() -> dict[str, bytes]:
    """A heating Crafty+ on V03.02."""
    return {
        CHAR_CURRENT_TEMP: u16(1830),
        CHAR_TARGET_TEMP: u16(1850),
        CHAR_BOOST_TEMP: u16(150),
        CHAR_BATTERY: u16(85),
        CHAR_LED_BRIGHTNESS: u16(70),
        CHAR_AUTO_OFF_SETTING: u16(120),
        CHAR_AUTO_OFF_COUNTDOWN: u16(90),
        CHAR_SERIAL: b"CY123456XYZ",
        CHAR_FIRMWARE: b"V03.02",
        CHAR_BLE_FIRMWARE: bytes([1, 2, 3]),
        CHAR_USE_HOURS: u16(12),
        CHAR_USE_MINUTES: u16(34),
        CHAR_PRJSTAT1: u16(MASK_PRJSTAT_CRAFTY_ACTIVE),
        CHAR_PRJSTAT2: u16(MASK_PRJSTAT2_SET_TEMP_REACHED | 0x1000),
        CHAR_SYSTEM_STATUS: u16(0),
        CHAR_BATTERY_STATUS1: u16(0),
        CHAR_BATTERY_STATUS2: u16(0),
    }


async def connect(client: FakeBleakClient) -> CraftyDevice:
    device = CraftyDevice(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)):
        await device.async_manual_update(make_ble_device(name="STORZ&BICKEL"))
    return device


async def test_connect_reads_a_crafty_plus() -> None:
    """Everything the spec lists is read, and the push characteristics subscribed."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    data = device.data

    assert device.is_connected
    assert data.model_name == "Crafty+"
    assert data.current_temp == 183
    assert data.set_temp == 185
    assert data.boost_temp == 15
    assert data.battery == 85
    assert data.led_brightness == 70
    assert data.auto_off_seconds == 120
    assert data.auto_off_countdown == 90
    assert data.serial_number == "CY123456"
    assert data.firmware_version == "V03.02"
    assert data.firmware_ble_version == "V1.2.3"
    assert data.heat_time == 12 * 60 + 34
    assert data.heater is True
    assert data.at_temperature is True
    assert data.auto_ble_shutdown is True
    assert data.error is False
    for uuid in (
        CHAR_CURRENT_TEMP, CHAR_BATTERY, CHAR_AUTO_OFF_COUNTDOWN, CHAR_PRJSTAT1, CHAR_PRJSTAT2
    ):
        assert uuid in client.notify_callbacks
    assert CHAR_TARGET_TEMP not in client.notify_callbacks


async def test_target_in_fahrenheit_is_converted() -> None:
    """A device set to °F reports °F ×10; it is read as °C (spec §3.1)."""
    values = crafty_plus_values()
    values[CHAR_TARGET_TEMP] = u16(3650)
    device = await connect(FakeBleakClient(values))
    assert device.data.set_temp == 185


async def test_old_firmware_skips_the_settings_characteristics() -> None:
    """Below V02.51 the settings side is not read and the heater cannot be switched."""
    values = {k: v for k, v in crafty_plus_values().items() if k not in SETTINGS_CHARS}
    values[CHAR_FIRMWARE] = b"V02.49"
    client = FakeBleakClient(values, missing=SETTINGS_CHARS)
    device = await connect(client)

    assert device.is_connected
    assert device.data.is_old_firmware is True
    assert device.data.model_name == "Crafty"
    assert device.data.heat_time == 12 * 60
    assert device.data.auto_off_seconds is None
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_heater(True)
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_auto_off_seconds(200)
    assert client.written == []


async def test_heater_writes_two_zero_bytes_and_tracks_the_write() -> None:
    """Heater on/off are separate characteristics written with `00 00` (spec §3)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_heater(False)
    assert client.written == [(CHAR_HEATER_OFF, b"\x00\x00")]
    assert device.data.heater_write is False
    assert device.data.is_assumed

    # The device confirms through PRJSTAT1.
    await client.notify_callbacks[CHAR_PRJSTAT1](None, bytearray(u16(0)))
    assert device.data.heater is False
    assert not device.data.is_assumed

    assert await device.async_set_heater(True)
    assert client.written[-1] == (CHAR_HEATER_ON, b"\x00\x00")


async def test_target_write_rewrites_the_boost() -> None:
    """Writing the target is followed by re-writing the boost (spec §3.2)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_target_temperature(190)
    assert client.written == [
        (CHAR_TARGET_TEMP, u16(1900)),
        (CHAR_BOOST_TEMP, u16(150)),
    ]
    assert device.data.set_temp_write == 190


async def test_auto_off_write_is_preceded_by_the_security_code() -> None:
    """The auto-off setting needs code 815 written first (spec §5.2)."""
    client = FakeBleakClient(crafty_plus_values())
    device = await connect(client)
    client.written.clear()

    assert await device.async_set_auto_off_seconds(200)
    assert client.written == [
        (CHAR_SECURITY_CODE, u16(SECURITY_CODE_AUTO_OFF)),
        (CHAR_AUTO_OFF_SETTING, u16(200)),
    ]
    assert device.data.auto_off_seconds == 200


async def test_prjstat2_settings_are_read_modify_write() -> None:
    """A settings bit is flipped in the whole word and the word re-read (spec §4.2)."""
    values = crafty_plus_values()
    client = FakeBleakClient(values)
    device = await connect(client)
    client.written.clear()
    values[CHAR_PRJSTAT2] = u16(0x1004 | 0x0001)

    assert await device.async_set_vibration(False)
    assert client.written == [(CHAR_PRJSTAT2, u16(0x1004 | 0x0001))]
    assert device.data.vibration is False

    client.written.clear()
    values[CHAR_PRJSTAT2] = u16(0x0004 | 0x0001)
    assert await device.async_set_auto_ble_shutdown(False)
    assert client.written == [(CHAR_PRJSTAT2, u16(0x0004 | 0x0001))]
    assert device.data.auto_ble_shutdown is False


async def test_find_device_needs_a_crafty_plus() -> None:
    """Find-my-Crafty sets PRJSTAT2 bit 3; the original Crafty has no such mode."""
    values = crafty_plus_values()
    client = FakeBleakClient(values)
    device = await connect(client)
    client.written.clear()
    assert await device.async_find_device()
    assert client.written == [(CHAR_PRJSTAT2, u16(0x1004 | 0x0008))]

    values[CHAR_FIRMWARE] = b"V02.60"
    device = await connect(FakeBleakClient(values))
    with pytest.raises(UnsupportedCommandError):
        await device.async_find_device()


async def test_pending_writes_are_dropped_when_the_device_is_off() -> None:
    """A queued write never turns a switched-off Crafty on (VOLCANO_BLE_SPEC.md §5)."""
    values = crafty_plus_values()
    values[CHAR_PRJSTAT1] = u16(0)
    client = FakeBleakClient(values)
    device = await connect(client)
    device.data.set_temp_write = 200
    await device.async_manual_update()
    assert device.data.set_temp_write is None
    assert (CHAR_TARGET_TEMP, u16(2000)) not in client.written
```

- [ ] **Step 3: Run to verify failure**

Run: `RUN_TESTS tests/test_crafty_ble.py -q`
Expected: FAIL — `ModuleNotFoundError: ... volcano_ble.crafty`

- [ ] **Step 4: Create `volcano_ble/crafty.py`**

```python
"""Crafty / Crafty+ protocol (CRAFTY_BLE_SPEC.md)."""

from __future__ import annotations

import asyncio
import logging

from .const import DeviceFamily
from .crafty_data import (
    MASK_PRJSTAT2_DISABLE_CHARGELED,
    MASK_PRJSTAT2_DISABLE_VIBRATION,
    MASK_PRJSTAT2_ENABLE_AUTOBLESHUTDOWN,
    MASK_PRJSTAT2_FIND_DEVICE,
    CraftyData,
    decode_target,
)
from .device import StorzBickelDevice, UnsupportedCommandError, _decode_ascii

_LOGGER = logging.getLogger(__name__)

_BASE = "-4c45-4b43-4942-265a524f5453"
SERVICE_CONTROL = "00000001" + _BASE
SERVICE_IDENTITY = "00000002" + _BASE
SERVICE_STATUS = "00000003" + _BASE

# Service 1 (spec §3)
CHAR_CURRENT_TEMP = "00000011" + _BASE
CHAR_TARGET_TEMP = "00000021" + _BASE
CHAR_BOOST_TEMP = "00000031" + _BASE
CHAR_BATTERY = "00000041" + _BASE
CHAR_LED_BRIGHTNESS = "00000051" + _BASE
CHAR_AUTO_OFF_SETTING = "00000061" + _BASE
CHAR_AUTO_OFF_COUNTDOWN = "00000071" + _BASE
CHAR_HEATER_ON = "00000081" + _BASE
CHAR_HEATER_OFF = "00000091" + _BASE
# Service 2 (spec §5.1)
CHAR_FIRMWARE = "00000032" + _BASE
CHAR_SERIAL = "00000052" + _BASE
CHAR_BLE_FIRMWARE = "00000072" + _BASE
# Service 3 (spec §4)
CHAR_USE_HOURS = "00000023" + _BASE
CHAR_BATTERY_STATUS1 = "00000063" + _BASE
CHAR_BATTERY_STATUS2 = "00000073" + _BASE
CHAR_SYSTEM_STATUS = "00000083" + _BASE
CHAR_PRJSTAT1 = "00000093" + _BASE
CHAR_SECURITY_CODE = "000001b3" + _BASE
CHAR_PRJSTAT2 = "000001c3" + _BASE
CHAR_FACTORY_RESET = "000001d3" + _BASE
CHAR_USE_MINUTES = "000001e3" + _BASE

# Spec §5.2. The factory-reset code (1000) is deliberately not defined:
# nothing here resets a device.
SECURITY_CODE_AUTO_OFF = 815
# The app writes an Int16 zero to either heater characteristic.
HEATER_PAYLOAD = bytearray(2)
SERIAL_LENGTH = 8


def _u16(data: bytearray) -> int:
    return int.from_bytes(data[:2], "little")


def _to_u16(value: int) -> bytearray:
    return bytearray(int(value).to_bytes(2, "little"))


class CraftyDevice(StorzBickelDevice):
    """A Crafty or Crafty+."""

    family = DeviceFamily.CRAFTY
    data_class = CraftyData
    data: CraftyData

    # -- reading -----------------------------------------------------------

    async def _async_read_initial(self) -> None:
        # The firmware string decides which characteristics exist (spec §6),
        # so it is read before everything that depends on it.
        await self._async_read_and_subscribe(
            SERVICE_IDENTITY, CHAR_FIRMWARE, self._parse_firmware, subscribe=False
        )
        await self._async_read_prjstat1(subscribe=True)
        reads = [
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_CURRENT_TEMP, self._parse_current_temp, subscribe=True
            ),
            self._async_read_target(),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_BOOST_TEMP, self._parse_boost, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_BATTERY, self._parse_battery, subscribe=True
            ),
            self._async_read_and_subscribe(
                SERVICE_CONTROL, CHAR_LED_BRIGHTNESS, self._parse_led, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_IDENTITY, CHAR_SERIAL, self._parse_serial, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_USE_HOURS, self._parse_hours, subscribe=False
            ),
            self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_PRJSTAT2, self._parse_prjstat2, subscribe=True
            ),
        ]
        if not self.data.is_old_firmware:
            reads += [
                self._async_read_optional(
                    SERVICE_CONTROL, CHAR_AUTO_OFF_SETTING, self._parse_auto_off_setting
                ),
                self._async_read_and_subscribe(
                    SERVICE_CONTROL,
                    CHAR_AUTO_OFF_COUNTDOWN,
                    self._parse_countdown,
                    subscribe=True,
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_USE_MINUTES, self._parse_minutes
                ),
                self._async_read_optional(
                    SERVICE_IDENTITY, CHAR_BLE_FIRMWARE, self._parse_ble_firmware
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_SYSTEM_STATUS, self._parse_system_status
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_BATTERY_STATUS1, self._parse_battery_status1
                ),
                self._async_read_optional(
                    SERVICE_STATUS, CHAR_BATTERY_STATUS2, self._parse_battery_status2
                ),
            ]
        await asyncio.gather(*reads)
        _LOGGER.debug("Initial Crafty characteristics read complete")
        self._after_data_updated()
        self._after_device_updated()

    async def _async_refresh(self) -> None:
        await self._async_read_and_subscribe(
            SERVICE_CONTROL, CHAR_CURRENT_TEMP, self._parse_current_temp, subscribe=False
        )

    async def _async_read_prjstat1(self, *, subscribe: bool) -> None:
        await self._async_read_and_subscribe(
            SERVICE_STATUS, CHAR_PRJSTAT1, self._parse_prjstat1, subscribe=subscribe
        )

    async def _async_read_target(self) -> None:
        await self._async_read_and_subscribe(
            SERVICE_CONTROL, CHAR_TARGET_TEMP, self._parse_target, subscribe=False
        )

    def _parse_firmware(self, data: bytearray) -> None:
        self.data.firmware_version = _decode_ascii(data)

    def _parse_ble_firmware(self, data: bytearray) -> None:
        # Three raw bytes, shown as V1.2.3 (spec §5.1).
        self.data.firmware_ble_version = "V" + ".".join(str(b) for b in data[:3])

    def _parse_serial(self, data: bytearray) -> None:
        self.data.serial_number = _decode_ascii(data)[:SERIAL_LENGTH]

    def _parse_current_temp(self, data: bytearray) -> None:
        self.data.current_temp = round(_u16(data) / 10)

    def _parse_target(self, data: bytearray) -> None:
        self.data.set_temp = decode_target(_u16(data))

    def _parse_boost(self, data: bytearray) -> None:
        self.data.boost_temp = round(_u16(data) / 10)

    def _parse_battery(self, data: bytearray) -> None:
        self.data.battery = _u16(data)

    def _parse_led(self, data: bytearray) -> None:
        self.data.led_brightness = _u16(data)

    def _parse_auto_off_setting(self, data: bytearray) -> None:
        self.data.auto_off_seconds = _u16(data)

    async def _parse_countdown(self, data: bytearray) -> None:
        self.data.auto_off_countdown = _u16(data)
        await self._async_try_ensure_written_values()

    def _parse_hours(self, data: bytearray) -> None:
        self.data.heat_hours = _u16(data)

    def _parse_minutes(self, data: bytearray) -> None:
        self.data.heat_minutes = _u16(data)

    def _parse_prjstat1(self, data: bytearray) -> None:
        self.data.apply_prj1(_u16(data))

    def _parse_prjstat2(self, data: bytearray) -> None:
        self.data.apply_prj2(_u16(data))

    def _parse_system_status(self, data: bytearray) -> None:
        self.data.system_status = _u16(data)
        self.data.apply_status_words()

    def _parse_battery_status1(self, data: bytearray) -> None:
        self.data.battery_status1 = _u16(data)
        self.data.apply_status_words()

    def _parse_battery_status2(self, data: bytearray) -> None:
        self.data.battery_status2 = _u16(data)

    # -- commands ----------------------------------------------------------

    def _require_settings_firmware(self) -> None:
        """Refuse what the pre-V02.51 firmware has no characteristic for."""
        if self.data.is_old_firmware is not False:
            msg = "needs Crafty firmware V02.51 or newer"
            raise UnsupportedCommandError(msg)

    async def async_set_heater(self, on: bool) -> bool:
        """Switch the heater; PRJSTAT1 bit 4 confirms."""
        self._require_settings_firmware()
        self.data.heater_write = on
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_HEATER_ON if on else CHAR_HEATER_OFF, HEATER_PAYLOAD
        )
        self._after_data_updated()
        return written

    async def async_set_target_temperature(self, target: float) -> bool:
        """Write the target, then re-write the boost as the vendor app does."""
        self.data.set_temp_write = int(target)
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_TARGET_TEMP, _to_u16(int(target) * 10)
        )
        if written and self.data.boost_temp is not None:
            await self._write_gatt(
                SERVICE_CONTROL, CHAR_BOOST_TEMP, _to_u16(self.data.boost_temp * 10)
            )
        if written:
            await self._async_read_target()
        self._after_data_updated()
        return written

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset in °C."""
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_BOOST_TEMP, _to_u16(offset * 10)
        )
        if written:
            self.data.boost_temp = offset
            self._after_data_updated()
        return written

    async def async_set_led_brightness(self, brightness: int) -> bool:
        """Set the LED brightness 0-100."""
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_LED_BRIGHTNESS, _to_u16(brightness)
        )
        if written:
            self.data.led_brightness = brightness
            self._after_data_updated()
        return written

    async def async_set_auto_off_seconds(self, seconds: int) -> bool:
        """Set the auto-off time; the security code unlocks the write (spec §5.2)."""
        self._require_settings_firmware()
        if not await self._write_gatt(
            SERVICE_STATUS, CHAR_SECURITY_CODE, _to_u16(SECURITY_CODE_AUTO_OFF)
        ):
            return False
        written = await self._write_gatt(
            SERVICE_CONTROL, CHAR_AUTO_OFF_SETTING, _to_u16(seconds)
        )
        if written:
            self.data.auto_off_seconds = seconds
            self._after_data_updated()
        return written

    async def _async_change_prjstat2(self, mask: int, *, set_bit: bool) -> bool:
        """Read-modify-write one PRJSTAT2 bit, then re-read the word (spec §4.2)."""
        if self.data.prj2 is None:
            return False
        word = (self.data.prj2 | mask) if set_bit else (self.data.prj2 & ~mask)
        written = await self._write_gatt(SERVICE_STATUS, CHAR_PRJSTAT2, _to_u16(word))
        if written:
            await self._async_read_and_subscribe(
                SERVICE_STATUS, CHAR_PRJSTAT2, self._parse_prjstat2, subscribe=False
            )
            self._after_data_updated()
        return written

    async def async_set_vibration(self, on: bool) -> bool:
        """Bit 0 is *disable vibration*."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_DISABLE_VIBRATION, set_bit=not on
        )

    async def async_set_charge_led(self, on: bool) -> bool:
        """Bit 1 is *disable charge LED*."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_DISABLE_CHARGELED, set_bit=not on
        )

    async def async_set_auto_ble_shutdown(self, on: bool) -> bool:
        """Bit 12 enables the automatic Bluetooth shutdown."""
        return await self._async_change_prjstat2(
            MASK_PRJSTAT2_ENABLE_AUTOBLESHUTDOWN, set_bit=on
        )

    async def async_find_device(self) -> bool:
        """Make a Crafty+ buzz for 30 s (bit 3); the app hides this below major 3."""
        if not self.data.is_plus:
            msg = "find my device needs a Crafty+"
            raise UnsupportedCommandError(msg)
        return await self._async_change_prjstat2(MASK_PRJSTAT2_FIND_DEVICE, set_bit=True)

    # -- pending writes ----------------------------------------------------

    async def _async_try_ensure_written_values(self) -> None:
        await self._async_read_target()
        await self._async_read_prjstat1(subscribe=False)
        if (
            self.data.heater_needs_write or self.data.set_temp_needs_write
        ) and not self.data.is_on:
            # Never turn the device on by replaying a command it missed.
            self.data.clear_open_writes()
        if (
            self.data.heater_needs_write
            and (heater := self.data.heater_write) is not None
        ):
            await self.async_set_heater(heater)
        if (
            self.data.set_temp_needs_write
            and (target := self.data.set_temp_write) is not None
        ):
            await self.async_set_target_temperature(target)
```

Register it in `families.py`: `DeviceFamily.CRAFTY: CraftyDevice` in `DEVICE_CLASSES` and restore `DATA_CLASSES` to the comprehension over `DEVICE_CLASSES`.

- [ ] **Step 5: Run the tests**

Run: `RUN_TESTS tests/test_crafty_ble.py tests/test_device.py tests/test_volcano_ble.py -q`
Expected: PASS. If `test_old_firmware_skips_the_settings_characteristics` fails because `FakeBleakClient.read_gatt_char` raises `KeyError` for a missing value, the read path is asking for a settings characteristic before the firmware string was parsed — check the ordering in `_async_read_initial`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests/fakes.py tests/test_crafty_ble.py tests/test_volcano_ble.py
git commit -m "Speak the Crafty protocol"
```

---

### Task 8: Crafty entities, coordinator commands, strings

**Files:**
- Modify: `coordinator.py`, `climate.py` (nothing — already generic), `sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `button.py`, `strings.json`, `translations/en.json`, `icons.json`
- Modify: `tests/__init__.py` (fake commands), `tests/test_entities_by_family.py` (golden block)
- Test: `tests/test_crafty_entities.py` (new)

**Interfaces:**
- Consumes the Task 6 keys and `CraftyData` fields; `FakeDevice` gains `async_set_boost_temperature`, `async_set_auto_off_seconds`, `async_set_charge_led`, `async_set_auto_ble_shutdown`, `async_find_device` recording `("boost_temp", v)`, `("auto_off_seconds", v)`, `("charge_led", v)`, `("auto_ble_shutdown", v)`, `("find_device", None)`.
- Produces coordinator methods `set_boost_temp(value: float)`, `set_auto_off_seconds(value: float)`, `set_charge_led(on)`, `set_auto_ble_shutdown(on)`, `find_device()` (named after the keys so `getattr(coordinator, "set_" + key)` keeps working).

- [ ] **Step 1: Extend the golden list and write the failing entity tests**

Add to `GOLDEN_ENTITIES` in `tests/test_entities_by_family.py`:

```python
    DeviceFamily.CRAFTY: {
        "climate": {"volcano"},
        "number": {"boost_temp", "led_brightness", "auto_off_seconds"},
        "switch": {"vibration", "charge_led", "auto_ble_shutdown", "auto_connect"},
        "sensor": {
            "battery", "auto_off_countdown", "heat_time", "rssi", "connected_addr",
            "prj1", "prj2", "system_status", "battery_status1", "battery_status2",
        },
        "binary_sensor": {
            "at_temperature", "heater", "boost_mode", "superboost_mode", "error",
            "needs_factory_reset", "find_mode", "connected",
        },
        "button": {"reconnect", "delayed_reconnect", "find_device"},
    },
```

Create `tests/test_crafty_entities.py`:

```python
"""Entity behaviour specific to the Crafty family."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION, DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, HVACAction,
)
from homeassistant.components.number import (
    ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_TEMPERATURE, SERVICE_TURN_OFF, STATE_OFF, STATE_ON,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.volcano_hybrid.volcano_ble import DeviceFamily, UnsupportedCommandError

from . import FakeDevice, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.parametrize(
    "device_family", [DeviceFamily.CRAFTY], indirect=True, ids=str
)


async def test_climate_has_no_fan_and_portable_limits(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """A Crafty climate stops at 210 °C and offers no fan mode."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.current_temp = 150
    data.set_temp = 185
    data.heater = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "climate", "volcano"))
    assert state is not None
    assert state.attributes["max_temp"] == 210
    assert state.attributes["min_temp"] == 40
    assert "fan_modes" not in state.attributes
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: state.entity_id, ATTR_TEMPERATURE: 190}, blocking=True,
    )
    assert ("target_temperature", 190) in mock_volcano.commands


async def test_sensors_and_binary_sensors(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    """Battery, countdown and the status words are reported as the data holds them."""
    mock_volcano.connected = True
    data = mock_volcano.data
    data.battery = 85
    data.auto_off_countdown = 90
    data.heat_hours, data.heat_minutes = 1, 30
    data.prj1 = 0x0030
    data.system_status = 0x0200
    data.apply_status_words()
    data.boost_mode = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    assert hass.states.get(get_entity_id(hass, "sensor", "battery")).state == "85"
    assert hass.states.get(get_entity_id(hass, "sensor", "auto_off_countdown")).state == "90"
    assert hass.states.get(get_entity_id(hass, "sensor", "system_status")).state == "0x0200"
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "error")).state == STATE_ON
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "boost_mode")).state == STATE_ON
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "superboost_mode")).state == STATE_OFF


@pytest.mark.parametrize(
    ("key", "value", "command"),
    [
        ("boost_temp", 20, ("boost_temp", 20)),
        ("auto_off_seconds", 200, ("auto_off_seconds", 200)),
        ("led_brightness", 50, ("led_brightness", 50)),
    ],
)
async def test_numbers(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
    value: int,
    command: tuple[str, int],
) -> None:
    """Each number writes through to the device."""
    entity_id = get_entity_id(hass, "number", key)
    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value}, blocking=True,
    )
    assert command in mock_volcano.commands


@pytest.mark.parametrize("key", ["charge_led", "auto_ble_shutdown", "vibration"])
async def test_switches(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
) -> None:
    """Each switch reflects the data and writes through."""
    mock_volcano.connected = True
    setattr(mock_volcano.data, key, True)
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    entity_id = get_entity_id(hass, "switch", key)
    assert hass.states.get(entity_id).state == STATE_ON
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert (key, False) in mock_volcano.commands


async def test_find_device_button_and_unsupported_error(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    """The button calls find-my-device; a refusal becomes a translated error."""
    entity_id = get_entity_id(hass, "button", "find_device")
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert ("find_device", None) in mock_volcano.commands

    mock_volcano.error = UnsupportedCommandError("not a Crafty+")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
    assert err.value.translation_key == "not_supported"
```

- [ ] **Step 2: Run to verify failure**

Run: `RUN_TESTS tests/test_entities_by_family.py tests/test_crafty_entities.py -q`
Expected: FAIL — the golden set is missing the Crafty entities / `get_entity_id` asserts.

- [ ] **Step 3: Coordinator commands**

Append to `VolcanoHybridCoordinator`:

```python
    async def set_boost_temp(self, offset: float) -> None:
        """Set the boost offset."""
        await self._async_command(self._device.async_set_boost_temperature(int(offset)))

    async def set_superboost_temp(self, offset: float) -> None:
        """Set the superboost offset."""
        await self._async_command(
            self._device.async_set_superboost_temperature(int(offset))
        )

    async def set_auto_off_seconds(self, seconds: float) -> None:
        """Set the auto-off time in seconds."""
        await self._async_command(self._device.async_set_auto_off_seconds(int(seconds)))

    async def set_charge_led(self, on: bool) -> None:
        """Enable or disable the charge LED."""
        await self._async_command(self._device.async_set_charge_led(on))

    async def set_auto_ble_shutdown(self, on: bool) -> None:
        """Enable or disable automatic Bluetooth shutdown."""
        await self._async_command(self._device.async_set_auto_ble_shutdown(on))

    async def find_device(self) -> None:
        """Make the device signal so it can be found."""
        await self._async_command(self._device.async_find_device())

    async def set_charge_optimization(self, on: bool) -> None:
        """Enable or disable charge optimisation."""
        await self._async_command(self._device.async_set_charge_optimization(on))

    async def set_charge_limit(self, on: bool) -> None:
        """Enable or disable the charge limit."""
        await self._async_command(self._device.async_set_charge_limit(on))

    async def set_boost_visualization(self, on: bool) -> None:
        """Show or hide boost on the display."""
        await self._async_command(self._device.async_set_boost_visualization(on))

    async def set_boost_timeout_disabled(self, on: bool) -> None:
        """Disable or re-enable the boost timeout."""
        await self._async_command(self._device.async_set_boost_timeout_disabled(on))

    async def set_permanent_bluetooth(self, on: bool) -> None:
        """Keep Bluetooth on while the device sleeps."""
        await self._async_command(self._device.async_set_permanent_bluetooth(on))

    async def set_brightness(self, brightness: float) -> None:
        """Set the display brightness 1-9."""
        await self._async_command(self._device.async_set_brightness(int(brightness)))
```

(The Qvap ones are added now too so Task 11 only touches platforms.)

`FakeDevice` in `tests/__init__.py` gains one recording method per device command above, e.g. `async def async_set_boost_temperature(self, offset: int) -> bool: return self._command("boost_temp", offset)`, `async def async_find_device(self) -> bool: return self._command("find_device", None)`, `async_set_superboost_temperature → "superboost_temp"`, `async_set_auto_off_seconds → "auto_off_seconds"`, `async_set_charge_led → "charge_led"`, `async_set_auto_ble_shutdown → "auto_ble_shutdown"`, `async_set_charge_optimization → "charge_optimization"`, `async_set_charge_limit → "charge_limit"`, `async_set_boost_visualization → "boost_visualization"`, `async_set_boost_timeout_disabled → "boost_timeout_disabled"`, `async_set_permanent_bluetooth → "permanent_bluetooth"`, `async_set_brightness → "brightness"`.

- [ ] **Step 4: Platform rows**

`number.py` — add to `SENSOR_DESCRIPTIONS` and to `NUMBER_KEYS` (after the Volcano rows; order within the tuple is cosmetic):

```python
    VolcanoSensor.BOOST_TEMP: NumberEntityDescription(
        key=VolcanoSensor.BOOST_TEMP,
        translation_key=VolcanoSensor.BOOST_TEMP,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=1,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    VolcanoSensor.AUTO_OFF_SECONDS: NumberEntityDescription(
        key=VolcanoSensor.AUTO_OFF_SECONDS,
        translation_key=VolcanoSensor.AUTO_OFF_SECONDS,
        device_class=NumberDeviceClass.DURATION,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=300,
        native_step=10,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
    ),
```

`switch.py` — `CHARGE_LED` and `AUTO_BLE_SHUTDOWN` rows shaped like the existing `VIBRATION` row (config category, disabled by default) and appended to `SWITCH_KEYS`.

`sensor.py` — rows: `BATTERY` (`SensorDeviceClass.BATTERY`, `%`, `MEASUREMENT`, enabled), `AUTO_OFF_COUNTDOWN` (`DURATION`, `UnitOfTime.SECONDS`, `MEASUREMENT`, enabled), `SYSTEM_STATUS`, `BATTERY_STATUS1`, `BATTERY_STATUS2` (like `PRJ1`: diagnostic, disabled, `value_fn=format_register`); all appended to `SENSOR_KEYS` with `always_available=False`. `HEAT_TIME` is reused as is (`CraftyData.heat_time` returns minutes).

`binary_sensor.py` — rows: `BOOST_MODE`, `SUPERBOOST_MODE` (no device class, enabled), `ERROR` (`PROBLEM`, diagnostic, enabled), `NEEDS_FACTORY_RESET` (`PROBLEM`, diagnostic, disabled), `FIND_MODE` (diagnostic, disabled); appended to `BINARY_SENSOR_KEYS` as `(key, False, None)`.

`button.py` — row `FIND_DEVICE` (`ButtonDeviceClass.IDENTIFY`, no category, enabled) wired to `coordinator.find_device`, `always_available=False` (it needs a connection).

- [ ] **Step 5: Strings and icons**

Add to `strings.json` `entity` (mirror in `en.json`): `number.boost_temp` "Boost temperature", `number.auto_off_seconds` "Auto off time", `switch.charge_led` "Charge LED", `switch.auto_ble_shutdown` "Automatic Bluetooth shutdown", `sensor.battery` "Battery", `sensor.auto_off_countdown` "Auto off countdown", `sensor.system_status` "System status", `sensor.battery_status1` "Battery status 1", `sensor.battery_status2` "Battery status 2", `binary_sensor.boost_mode` "Boost", `binary_sensor.superboost_mode` "Superboost", `binary_sensor.error` "Error", `binary_sensor.needs_factory_reset` "Needs factory reset", `binary_sensor.find_mode` "Find mode active", `button.find_device` "Find device".

`icons.json`: `number.boost_temp` `mdi:thermometer-plus`, `number.auto_off_seconds` `mdi:timer-off-outline`, `switch.charge_led` `mdi:led-on`, `switch.auto_ble_shutdown` `mdi:bluetooth-off`, `sensor.auto_off_countdown` `mdi:timer-sand`, `sensor.system_status` / `battery_status1` / `battery_status2` `mdi:memory`, `binary_sensor.boost_mode` `mdi:rocket-launch-outline`, `binary_sensor.superboost_mode` `mdi:rocket-launch`, `binary_sensor.find_mode` `mdi:vibrate`, `button.find_device` `mdi:map-marker-question`.

- [ ] **Step 6: Run the suite**

Run: `RUN_TESTS`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A custom_components tests
git commit -m "Expose the Crafty as entities"
```

---

### Task 9: Qvap frame codec

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/qvap_frames.py`
- Test: `tests/test_qvap_frames.py` (new)

**Interfaces:**
- Produces constants `FRAME_LENGTH = 20`, `CMD_STATUS = 0x01`, `CMD_FIRMWARE = 0x02`, `CMD_USAGE = 0x04`, `CMD_IDENTITY = 0x05`, `CMD_SETTINGS = 0x06`, `CMD_FIND_DEVICE = 0x0D`, `CMD_ADVERTISING = 0x1D`, `CMD_BOOTLOADER_SWITCH = 0x0C`, `CMD_BOOTLOADER = 0x30`, `FORBIDDEN_COMMANDS = frozenset({0x0C, 0x30})`; masks `MASK_SET_TEMP = 0x02`, `MASK_BOOST = 0x04`, `MASK_SUPERBOOST = 0x08`, `MASK_HEATER = 0x20`, `MASK_SETTINGS = 0x80`; settings bits `BIT_FAHRENHEIT = 0x01`, `BIT_SETPOINT_REACHED = 0x02`, `BIT_CHARGE_OPTIMIZATION = 0x08`, `BIT_TARGET_CHANGED = 0x10`, `BIT_CHARGE_LIMIT = 0x20`, `BIT_BOOST_VISUALIZATION = 0x40`, `BIT2_PERMANENT_BLUETOOTH = 0x01`; cmd-06 masks `CMD6_BRIGHTNESS = 0x01`, `CMD6_VIBRATION = 0x08`, `CMD6_BOOST_TIMEOUT = 0x10`; `APP_RUNNING = 0x01`, `APP_INVALID = 0x10`, `BOOTLOADER_INVALID = 0x20`.
- Produces dataclasses `QvapStatus(current_temp, target_temp, boost, superboost, battery, countdown, heater_mode, charging, settings, settings2)`, `QvapFirmware(application_running, invalid_application, invalid_bootloader, firmware_version, bootloader_version)`, `QvapUsage(heater_minutes, charging_minutes)`, `QvapIdentity(serial, color_index)`, `QvapSettings(brightness, vibration, boost_timeout_disabled)`.
- Produces builders `build_request(cmd) -> bytes`, `build_target_write(celsius: int)`, `build_boost_write(offset)`, `build_superboost_write(offset)`, `build_heater_write(on: bool)`, `build_settings_write(bits: int, mask: int, bits2: int = 0, mask2: int = 0)`, `build_settings6_write(mask, brightness=0, vibration=False, timeout_disabled=False)`, `build_find_device()`; parsers `parse_status`, `parse_firmware`, `parse_usage`, `parse_identity`, `parse_settings6`, `parse_advertising(frame) -> bool`. Parsers raise `ValueError` on a wrong command byte or a short frame.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_qvap_frames.py`:

```python
"""Byte-exact tests for the Venty/Veazy frame codec (VENTY_BLE_SPEC.md §2-3)."""

from __future__ import annotations

import pytest

from custom_components.volcano_hybrid.volcano_ble import qvap_frames as f

# A status reply: 183.8 °C current, 186.0 °C target, boost 10, superboost 20,
# battery 85 %, 120 s countdown, boost mode, charger on, settings 0x0A
# (setpoint reached + charge optimisation), settings2 permanent BT.
STATUS = bytes(
    [0x01, 0x00, 0x2E, 0x07, 0x44, 0x07, 10, 20, 85, 0x78, 0x00, 2, 0, 1, 0x0A, 0, 0x01, 0, 0, 0]
)


def test_parse_status() -> None:
    status = f.parse_status(STATUS)
    assert status.current_temp == 184
    assert status.target_temp == 186
    assert status.boost == 10
    assert status.superboost == 20
    assert status.battery == 85
    assert status.countdown == 120
    assert status.heater_mode == 2
    assert status.charging is True
    assert status.settings == 0x0A
    assert status.settings2 == 0x01


def test_parse_status_without_settings2() -> None:
    """Older firmware answers 15 bytes; settings2 is then unknown."""
    status = f.parse_status(STATUS[:15])
    assert status.settings2 is None


def test_parse_status_rejects_other_frames() -> None:
    with pytest.raises(ValueError, match="0x02"):
        f.parse_status(bytes([0x02]) + STATUS[1:])
    with pytest.raises(ValueError, match="short"):
        f.parse_status(STATUS[:14])


def test_build_request_is_a_zeroed_20_byte_frame() -> None:
    frame = f.build_request(f.CMD_FIRMWARE)
    assert len(frame) == 20
    assert frame[0] == 0x02
    assert not any(frame[1:])


def test_build_target_write() -> None:
    frame = f.build_target_write(185)
    assert frame[0] == 0x01
    assert frame[1] == f.MASK_SET_TEMP
    assert frame[4:6] == (1850).to_bytes(2, "little")
    assert not any(frame[6:])


def test_build_boost_and_superboost_writes() -> None:
    assert f.build_boost_write(12)[1:7] == bytes([f.MASK_BOOST, 0, 0, 0, 0, 12])
    assert f.build_superboost_write(15)[1:8] == bytes([f.MASK_SUPERBOOST, 0, 0, 0, 0, 0, 15])


def test_build_heater_write_only_toggles_between_off_and_normal() -> None:
    """Modes 2/3 are never written: entering boost over BLE is speculative."""
    on = f.build_heater_write(True)
    off = f.build_heater_write(False)
    assert on[1] == off[1] == f.MASK_HEATER
    assert on[11] == 1
    assert off[11] == 0


def test_build_settings_write_is_masked() -> None:
    frame = f.build_settings_write(f.BIT_CHARGE_LIMIT, f.BIT_CHARGE_LIMIT)
    assert frame[1] == f.MASK_SETTINGS
    assert frame[14] == 0x20
    assert frame[15] == 0x20
    clear = f.build_settings_write(0, f.BIT_CHARGE_LIMIT, 0, f.BIT2_PERMANENT_BLUETOOTH)
    assert clear[14:18] == bytes([0x00, 0x20, 0x00, 0x01])


def test_build_settings6_write_is_seven_bytes() -> None:
    frame = f.build_settings6_write(f.CMD6_BRIGHTNESS, brightness=9)
    assert frame == bytes([0x06, 0x01, 9, 0, 0, 0, 0])
    frame = f.build_settings6_write(f.CMD6_VIBRATION, vibration=True)
    assert frame == bytes([0x06, 0x08, 0, 0, 0, 1, 0])
    frame = f.build_settings6_write(f.CMD6_BOOST_TIMEOUT, timeout_disabled=True)
    assert frame == bytes([0x06, 0x10, 0, 0, 0, 0, 1])


def test_build_find_device() -> None:
    assert f.build_find_device()[:2] == bytes([0x0D, 0x01])


def test_parse_firmware_decodes_the_strings() -> None:
    """Versions are UTF-8 at offsets 2 and 11, not raw bytes (spec §3.1)."""
    frame = bytes([0x02, 0x01]) + b"V01.09" + bytes(3) + b"V00.05" + bytes(3)
    firmware = f.parse_firmware(frame)
    assert firmware.application_running is True
    assert firmware.invalid_application is False
    assert firmware.invalid_bootloader is False
    assert firmware.firmware_version == "V01.09"
    assert firmware.bootloader_version == "V00.05"

    in_bootloader = f.parse_firmware(bytes([0x02, 0x30]) + frame[2:])
    assert in_bootloader.application_running is False
    assert in_bootloader.invalid_application is True
    assert in_bootloader.invalid_bootloader is True


def test_parse_usage() -> None:
    frame = bytes([0x04]) + (100000).to_bytes(3, "little") + (5000).to_bytes(3, "little")
    frame += bytes(20 - len(frame))
    usage = f.parse_usage(frame)
    assert usage.heater_minutes == 100000
    assert usage.charging_minutes == 5000


def test_parse_identity() -> None:
    frame = bytearray(20)
    frame[0] = 0x05
    frame[9:15] = b"123456"
    frame[15:17] = b"VZ"
    frame[18] = 3
    identity = f.parse_identity(bytes(frame))
    assert identity.serial == "VZ123456"
    assert identity.color_index == 3
    assert f.parse_identity(bytes(frame[:18])).color_index is None


def test_parse_settings6() -> None:
    settings = f.parse_settings6(bytes([0x06, 0, 7, 0, 0, 1, 0]))
    assert settings.brightness == 7
    assert settings.vibration is True
    assert settings.boost_timeout_disabled is False


def test_parse_advertising() -> None:
    assert f.parse_advertising(bytes([0x1D, 0x10])) is True
    assert f.parse_advertising(bytes([0x1D, 0x00])) is False


def test_forbidden_commands_are_the_bootloader_ones() -> None:
    assert f.FORBIDDEN_COMMANDS == {0x0C, 0x30}
```

- [ ] **Step 2: Run to verify failure**

Run: `RUN_TESTS tests/test_qvap_frames.py -q`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Create `volcano_ble/qvap_frames.py`**

```python
"""
Frames of the Venty/Veazy ("Qvap") protocol, built and parsed byte for byte.

Every table here mirrors one in VENTY_BLE_SPEC.md; nothing in this module
touches Bluetooth, so it can be tested against the spec's own examples.
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_LENGTH = 20
SETTINGS6_LENGTH = 7

# Command ids (spec §2, §3)
CMD_STATUS = 0x01
CMD_FIRMWARE = 0x02
CMD_USAGE = 0x04
CMD_IDENTITY = 0x05
CMD_SETTINGS = 0x06
CMD_BOOTLOADER_SWITCH = 0x0C
CMD_FIND_DEVICE = 0x0D
CMD_ADVERTISING = 0x1D
CMD_BOOTLOADER = 0x30
# Spec §3.8: these put the device into, or drive, its bootloader.
FORBIDDEN_COMMANDS = frozenset({CMD_BOOTLOADER_SWITCH, CMD_BOOTLOADER})

# Status write masks, byte 1 (spec §2.2)
MASK_SET_TEMP = 0x02
MASK_BOOST = 0x04
MASK_SUPERBOOST = 0x08
MASK_HEATER = 0x20
MASK_SETTINGS = 0x80

# Settings bits, byte 14 (spec §2.3)
BIT_FAHRENHEIT = 0x01
BIT_SETPOINT_REACHED = 0x02
BIT_CHARGE_OPTIMIZATION = 0x08
BIT_TARGET_CHANGED = 0x10
BIT_CHARGE_LIMIT = 0x20
BIT_BOOST_VISUALIZATION = 0x40
# Settings2 bits, byte 16
BIT2_PERMANENT_BLUETOOTH = 0x01

# Command 0x06 masks (spec §3.4)
CMD6_BRIGHTNESS = 0x01
CMD6_VIBRATION = 0x08
CMD6_BOOST_TIMEOUT = 0x10

# Firmware flags, command 0x02 byte 1 (spec §3.1)
APP_RUNNING = 0x01
APP_INVALID = 0x10
BOOTLOADER_INVALID = 0x20

HEATER_MODE_OFF = 0
HEATER_MODE_ON = 1
HEATER_MODE_BOOST = 2
HEATER_MODE_SUPERBOOST = 3

_STATUS_MIN = 15
_STATUS_WITH_SETTINGS2 = 17
_FIRMWARE_MIN = 19
_USAGE_MIN = 7
_IDENTITY_MIN = 17
_IDENTITY_WITH_COLOR = 19
_ADVERTISING_MIN = 2


@dataclass(frozen=True)
class QvapStatus:
    """One command-0x01 reply (spec §2.1)."""

    current_temp: int
    target_temp: int
    boost: int
    superboost: int
    battery: int
    countdown: int
    heater_mode: int
    charging: bool
    settings: int
    settings2: int | None


@dataclass(frozen=True)
class QvapFirmware:
    """One command-0x02 reply (spec §3.1)."""

    application_running: bool
    invalid_application: bool
    invalid_bootloader: bool
    firmware_version: str
    bootloader_version: str


@dataclass(frozen=True)
class QvapUsage:
    """One command-0x04 reply (spec §3.2)."""

    heater_minutes: int
    charging_minutes: int


@dataclass(frozen=True)
class QvapIdentity:
    """One command-0x05 reply (spec §3.3)."""

    serial: str
    color_index: int | None


@dataclass(frozen=True)
class QvapSettings:
    """One command-0x06 reply (spec §3.4)."""

    brightness: int
    vibration: bool
    boost_timeout_disabled: bool


def _check(frame: bytes, cmd: int, minimum: int) -> None:
    if not frame or frame[0] != cmd:
        msg = f"expected command 0x{cmd:02x}, got 0x{frame[0]:02x}" if frame else "empty"
        raise ValueError(msg)
    if len(frame) < minimum:
        msg = f"frame too short for command 0x{cmd:02x}: {len(frame)} < {minimum}"
        raise ValueError(msg)


def _u16(frame: bytes, offset: int) -> int:
    return int.from_bytes(frame[offset : offset + 2], "little")


# -- builders ----------------------------------------------------------------


def _frame(cmd: int, mask: int = 0, fields: dict[int, int] | None = None) -> bytes:
    frame = bytearray(FRAME_LENGTH)
    frame[0] = cmd
    frame[1] = mask
    for offset, value in (fields or {}).items():
        frame[offset] = value & 0xFF
    return bytes(frame)


def build_request(cmd: int) -> bytes:
    """A read request: the command id and nothing else."""
    return _frame(cmd)


def build_target_write(celsius: int) -> bytes:
    """Set the target temperature (×10, bytes 4-5)."""
    raw = celsius * 10
    return _frame(CMD_STATUS, MASK_SET_TEMP, {4: raw, 5: raw >> 8})


def build_boost_write(offset: int) -> bytes:
    """Set the boost offset (byte 6)."""
    return _frame(CMD_STATUS, MASK_BOOST, {6: offset})


def build_superboost_write(offset: int) -> bytes:
    """Set the superboost offset (byte 7)."""
    return _frame(CMD_STATUS, MASK_SUPERBOOST, {7: offset})


def build_heater_write(on: bool) -> bytes:
    """Switch the heater between off and normal heating (byte 11)."""
    return _frame(CMD_STATUS, MASK_HEATER, {11: HEATER_MODE_ON if on else HEATER_MODE_OFF})


def build_settings_write(bits: int, mask: int, bits2: int = 0, mask2: int = 0) -> bytes:
    """Change settings bits: values in bytes 14/16, which bits in 15/17."""
    return _frame(CMD_STATUS, MASK_SETTINGS, {14: bits, 15: mask, 16: bits2, 17: mask2})


def build_settings6_write(
    mask: int,
    *,
    brightness: int = 0,
    vibration: bool = False,
    timeout_disabled: bool = False,
) -> bytes:
    """The 7-byte command 0x06 write."""
    return bytes(
        [CMD_SETTINGS, mask, brightness & 0xFF, 0, 0, int(vibration), int(timeout_disabled)]
    )


def build_find_device() -> bytes:
    """Make the device signal its position."""
    return _frame(CMD_FIND_DEVICE, 0x01)


# -- parsers -----------------------------------------------------------------


def parse_status(frame: bytes) -> QvapStatus:
    """Decode a command-0x01 reply."""
    _check(frame, CMD_STATUS, _STATUS_MIN)
    return QvapStatus(
        current_temp=round(_u16(frame, 2) / 10),
        target_temp=round(_u16(frame, 4) / 10),
        boost=frame[6],
        superboost=frame[7],
        battery=frame[8],
        countdown=_u16(frame, 9),
        heater_mode=frame[11],
        charging=frame[13] > 0,
        settings=frame[14],
        settings2=frame[16] if len(frame) >= _STATUS_WITH_SETTINGS2 else None,
    )


def parse_firmware(frame: bytes) -> QvapFirmware:
    """Decode a command-0x02 reply; the versions are UTF-8 strings."""
    _check(frame, CMD_FIRMWARE, _FIRMWARE_MIN)
    flags = frame[1]
    return QvapFirmware(
        application_running=bool(flags & APP_RUNNING),
        invalid_application=bool(flags & APP_INVALID),
        invalid_bootloader=bool(flags & BOOTLOADER_INVALID),
        firmware_version=frame[2:8].decode("utf-8", "replace").strip("\x00 "),
        bootloader_version=frame[11:17].decode("utf-8", "replace").strip("\x00 "),
    )


def parse_usage(frame: bytes) -> QvapUsage:
    """Decode a command-0x04 reply: two uint24 minute counters."""
    _check(frame, CMD_USAGE, _USAGE_MIN)
    return QvapUsage(
        heater_minutes=int.from_bytes(frame[1:4], "little"),
        charging_minutes=int.from_bytes(frame[4:7], "little"),
    )


def parse_identity(frame: bytes) -> QvapIdentity:
    """Decode a command-0x05 reply: prefix + serial, optional colour."""
    _check(frame, CMD_IDENTITY, _IDENTITY_MIN)
    serial = (frame[15:17] + frame[9:15]).decode("utf-8", "replace").strip("\x00 ")
    color = frame[18] if len(frame) >= _IDENTITY_WITH_COLOR else None
    return QvapIdentity(serial=serial, color_index=color)


def parse_settings6(frame: bytes) -> QvapSettings:
    """Decode a command-0x06 reply."""
    _check(frame, CMD_SETTINGS, SETTINGS6_LENGTH)
    return QvapSettings(
        brightness=frame[2],
        vibration=frame[5] != 0,
        boost_timeout_disabled=frame[6] != 0,
    )


def parse_advertising(frame: bytes) -> bool:
    """Decode a command-0x1D reply: whether find-my-device mode is active."""
    _check(frame, CMD_ADVERTISING, _ADVERTISING_MIN)
    return bool(frame[1] & 0x10)
```

- [ ] **Step 4: Run the tests**

Run: `RUN_TESTS tests/test_qvap_frames.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble/qvap_frames.py tests/test_qvap_frames.py
git commit -m "Build and parse the Venty/Veazy frames"
```

---

### Task 10: `QvapData` and `QvapDevice` (Venty + Veazy)

**Files:**
- Create: `custom_components/volcano_hybrid/volcano_ble/qvap_data.py`, `volcano_ble/qvap.py`
- Modify: `volcano_ble/const.py` (keys), `volcano_ble/families.py`
- Test: `tests/test_qvap_data.py`, `tests/test_qvap_ble.py` (new); `tests/fakes.py` (add `SimulatedQvap`)

**Interfaces:**
- Produces `VolcanoSensor` keys: `SUPERBOOST_TEMP = "superboost_temp"`, `HEATER_MODE = "heater_mode"`, `CHARGING = "charging"`, `CHARGE_OPTIMIZATION = "charge_optimization"`, `CHARGE_LIMIT = "charge_limit"`, `BOOST_VISUALIZATION = "boost_visualization"`, `BOOST_TIMEOUT_DISABLED = "boost_timeout_disabled"`, `PERMANENT_BLUETOOTH = "permanent_bluetooth"` (switch, Veazy), `PERMANENT_BLUETOOTH_ENABLED = "permanent_bluetooth_enabled"` (binary sensor, Venty), `BRIGHTNESS = "brightness"`, `CHARGING_TIME = "charging_time"`, `COLOR = "color"`, `BOOTLOADER_MODE = "bootloader_mode"`, `TARGET_CHANGED_ON_DEVICE = "target_changed_on_device"`.
- Produces `QvapData(DeviceData)` (abstract family), `VentyData`, `VeazyData`; fields `battery`, `charging`, `boost_temp`, `superboost_temp`, `heater_mode`, `auto_off_countdown`, `showing_celsius`, `charge_optimization`, `charge_limit`, `boost_visualization`, `permanent_bluetooth`, `brightness`, `vibration`, `boost_timeout_disabled`, `heat_time`, `charging_time`, `color`, `bootloader_mode`, `target_changed_on_device`, `find_mode`, `invalid_application`, `invalid_bootloader`; properties `boost_mode`, `superboost_mode`, `heater_mode_name`, `permanent_bluetooth_enabled`; `apply_status(QvapStatus)`, `apply_firmware(QvapFirmware)`, `apply_usage`, `apply_identity`, `apply_settings6`. `HEATER_MODE_OPTIONS = ["off", "heating", "boost", "superboost"]`, `COLOR_OPTIONS = ["black", "blue", "pink", "orange"]`.
- Produces `QvapDevice(StorzBickelDevice)` with `family` set per subclass `VentyDevice` / `VeazyDevice`, `QVAP_POLL_INTERVAL = 1.0`, `QVAP_SLOW_POLL_EVERY = 30`, `SERVICE_UUID`, `CHAR_CONTROL`, `CHAR_GAP_NAME`; `_async_poll_once()`; commands `async_set_heater`, `async_set_target_temperature`, `async_set_boost_temperature`, `async_set_superboost_temperature`, `async_set_showing_celsius`, `async_set_charge_optimization`, `async_set_charge_limit`, `async_set_boost_visualization`, `async_set_permanent_bluetooth` (Veazy), `async_set_brightness`, `async_set_vibration`, `async_set_boost_timeout_disabled`, `async_find_device`.
- Produces `tests/fakes.py::SimulatedQvap(client, *, veazy=False)` — attaches to a `FakeBleakClient`, keeps a status state, answers every write to `CHAR_CONTROL` by calling the notify callback with the reply frame.

- [ ] **Step 1: Keys**

Append the fourteen keys above to `VolcanoSensor`.

- [ ] **Step 2: Data tests**

Create `tests/test_qvap_data.py`:

```python
"""Tests for the Venty/Veazy state decoded from frames."""

from __future__ import annotations

from custom_components.volcano_hybrid.volcano_ble import qvap_frames as f
from custom_components.volcano_hybrid.volcano_ble.const import DeviceFamily, VolcanoSensor
from custom_components.volcano_hybrid.volcano_ble.qvap_data import VeazyData, VentyData

from . import FakeDevice


def _status(**overrides: int | bool | None) -> f.QvapStatus:
    values: dict = {
        "current_temp": 184, "target_temp": 186, "boost": 10, "superboost": 20,
        "battery": 85, "countdown": 120, "heater_mode": 2, "charging": True,
        "settings": f.BIT_SETPOINT_REACHED | f.BIT_CHARGE_OPTIMIZATION,
        "settings2": f.BIT2_PERMANENT_BLUETOOTH,
    }
    values.update(overrides)
    return f.QvapStatus(**values)


def test_apply_status_on_a_venty() -> None:
    data: VentyData = FakeDevice(DeviceFamily.VENTY).data
    data.apply_status(_status())
    assert data.current_temp == 184
    assert data.set_temp == 186
    assert data.boost_temp == 10
    assert data.superboost_temp == 20
    assert data.battery == 85
    assert data.auto_off_countdown == 120
    assert data.heater is True
    assert data.heater_mode == 2
    assert data.heater_mode_name == "boost"
    assert data.boost_mode is True
    assert data.superboost_mode is False
    assert data.charging is True
    assert data.at_temperature is True
    assert data.showing_celsius is True
    assert data.charge_optimization is True
    assert data.charge_limit is False
    assert data.boost_visualization is False
    assert data.target_changed_on_device is False
    assert data.permanent_bluetooth is True
    assert data.permanent_bluetooth_enabled is True

    data.apply_status(_status(heater_mode=0, settings=f.BIT_FAHRENHEIT, settings2=None))
    assert data.heater is False
    assert data.heater_mode_name == "off"
    assert data.showing_celsius is False
    assert data.permanent_bluetooth is True  # unchanged when the frame omits it


def test_veazy_inverts_the_visualization_bit() -> None:
    data: VeazyData = FakeDevice(DeviceFamily.VEAZY).data
    data.apply_status(_status(settings=f.BIT_BOOST_VISUALIZATION))
    assert data.boost_visualization is False
    data.apply_status(_status(settings=0))
    assert data.boost_visualization is True


def test_apply_firmware_and_bootloader_mode() -> None:
    data: VentyData = FakeDevice(DeviceFamily.VENTY).data
    data.apply_firmware(f.QvapFirmware(True, False, False, "V01.09", "V00.05"))
    assert data.firmware_version == "V01.09"
    assert data.bootloader_version == "V00.05"
    assert data.bootloader_mode is False
    data.apply_firmware(f.QvapFirmware(False, True, False, "V01.09", "V00.05"))
    assert data.bootloader_mode is True
    assert data.invalid_application is True


def test_apply_usage_identity_and_settings6() -> None:
    data: VeazyData = FakeDevice(DeviceFamily.VEAZY).data
    data.apply_usage(f.QvapUsage(150, 40))
    assert data.heat_time == 150
    assert data.charging_time == 40
    data.apply_identity(f.QvapIdentity("VZ654321", 3))
    assert data.serial_number == "VZ654321"
    assert data.color == "pink"
    data.apply_identity(f.QvapIdentity("VZ654321", 9))
    assert data.color == "black"
    data.apply_settings6(f.QvapSettings(7, True, False))
    assert data.brightness == 7
    assert data.vibration is True
    assert data.boost_timeout_disabled is False


def test_capabilities_differ_between_venty_and_veazy() -> None:
    venty = FakeDevice(DeviceFamily.VENTY).data
    veazy = FakeDevice(DeviceFamily.VEAZY).data
    assert VolcanoSensor.PERMANENT_BLUETOOTH_ENABLED in venty.capabilities
    assert VolcanoSensor.PERMANENT_BLUETOOTH not in venty.capabilities
    assert VolcanoSensor.PERMANENT_BLUETOOTH in veazy.capabilities
    assert VolcanoSensor.COLOR in veazy.capabilities
    assert VolcanoSensor.COLOR not in venty.capabilities
    assert venty.model_name == "Venty"
    assert veazy.model_name == "Veazy"
```

- [ ] **Step 3: Create `volcano_ble/qvap_data.py`**

```python
"""State of a Venty or Veazy, filled from the frames in qvap_frames."""

from __future__ import annotations

from .const import (
    PORTABLE_MAX_TEMP,
    PORTABLE_MIN_DISPLAY_TEMP,
    PORTABLE_MIN_TEMP,
    DeviceFamily,
    VolcanoSensor,
)
from .data import DeviceData, VolcanoHybridDataStatusProvider
from .qvap_frames import (
    BIT2_PERMANENT_BLUETOOTH,
    BIT_BOOST_VISUALIZATION,
    BIT_CHARGE_LIMIT,
    BIT_CHARGE_OPTIMIZATION,
    BIT_FAHRENHEIT,
    BIT_SETPOINT_REACHED,
    BIT_TARGET_CHANGED,
    HEATER_MODE_BOOST,
    HEATER_MODE_OFF,
    HEATER_MODE_SUPERBOOST,
    QvapFirmware,
    QvapIdentity,
    QvapSettings,
    QvapStatus,
    QvapUsage,
)

HEATER_MODE_OPTIONS = ["off", "heating", "boost", "superboost"]
# Spec §3.3: 2 blue, 3 pink, 4 orange, anything else black.
COLOR_OPTIONS = ["black", "blue", "pink", "orange"]
_COLOR_BY_INDEX = {2: "blue", 3: "pink", 4: "orange"}

_SHARED_CAPABILITIES = frozenset(
    {
        VolcanoSensor.VOLCANO, VolcanoSensor.FIRMWARE,
        VolcanoSensor.BOOST_TEMP, VolcanoSensor.SUPERBOOST_TEMP, VolcanoSensor.BRIGHTNESS,
        VolcanoSensor.SHOWING_CELSIUS, VolcanoSensor.VIBRATION,
        VolcanoSensor.CHARGE_OPTIMIZATION, VolcanoSensor.CHARGE_LIMIT,
        VolcanoSensor.BOOST_VISUALIZATION, VolcanoSensor.BOOST_TIMEOUT_DISABLED,
        VolcanoSensor.AUTO_CONNECT,
        VolcanoSensor.BATTERY, VolcanoSensor.AUTO_OFF_COUNTDOWN, VolcanoSensor.HEATER_MODE,
        VolcanoSensor.HEAT_TIME, VolcanoSensor.CHARGING_TIME, VolcanoSensor.RSSI,
        VolcanoSensor.CONNECTED_ADDR,
        VolcanoSensor.AT_TEMPERATURE, VolcanoSensor.HEATER_ACTIVE, VolcanoSensor.CHARGING,
        VolcanoSensor.BOOST_MODE, VolcanoSensor.SUPERBOOST_MODE,
        VolcanoSensor.TARGET_CHANGED_ON_DEVICE, VolcanoSensor.BOOTLOADER_MODE,
        VolcanoSensor.CONNECTED,
        VolcanoSensor.RECONNECT, VolcanoSensor.DELAYED_RECONNECT, VolcanoSensor.FIND_DEVICE,
    }
)


class QvapData(DeviceData):
    """Data object for the Venty/Veazy protocol family."""

    MIN_TEMP = PORTABLE_MIN_TEMP
    MAX_TEMP = PORTABLE_MAX_TEMP
    MIN_DISPLAY_TEMP = PORTABLE_MIN_DISPLAY_TEMP
    # The Veazy reports the visualisation bit inverted (spec §2.3).
    INVERT_BOOST_VISUALIZATION = False

    def __init__(self, device: VolcanoHybridDataStatusProvider) -> None:
        """Initialize the Qvap fields."""
        super().__init__(device)
        self.battery: int | None = None
        self.charging: bool | None = None
        self.boost_temp: int | None = None
        self.superboost_temp: int | None = None
        self.heater_mode: int | None = None
        self.auto_off_countdown: int | None = None
        self.showing_celsius: bool | None = None
        self.charge_optimization: bool | None = None
        self.charge_limit: bool | None = None
        self.boost_visualization: bool | None = None
        self.permanent_bluetooth: bool | None = None
        self.target_changed_on_device: bool | None = None
        self.brightness: int | None = None
        self.vibration: bool | None = None
        self.boost_timeout_disabled: bool | None = None
        self.heat_time: int | None = None
        self.charging_time: int | None = None
        self.color: str | None = None
        self.bootloader_mode: bool | None = None
        self.invalid_application: bool | None = None
        self.invalid_bootloader: bool | None = None
        self.find_mode: bool | None = None

    @property
    def boost_mode(self) -> bool | None:
        """Whether the heater is in boost mode."""
        return None if self.heater_mode is None else self.heater_mode == HEATER_MODE_BOOST

    @property
    def superboost_mode(self) -> bool | None:
        """Whether the heater is in superboost mode."""
        if self.heater_mode is None:
            return None
        return self.heater_mode == HEATER_MODE_SUPERBOOST

    @property
    def heater_mode_name(self) -> str | None:
        """The heater mode as an enum state."""
        if self.heater_mode is None or self.heater_mode >= len(HEATER_MODE_OPTIONS):
            return None
        return HEATER_MODE_OPTIONS[self.heater_mode]

    @property
    def permanent_bluetooth_enabled(self) -> bool | None:
        """The same setting under the read-only key the Venty exposes it as."""
        return self.permanent_bluetooth

    def apply_status(self, status: QvapStatus) -> None:
        """Take over a command-0x01 reply (spec §2.1, §2.3)."""
        self.current_temp = status.current_temp
        self.set_temp = status.target_temp
        self.boost_temp = status.boost
        self.superboost_temp = status.superboost
        self.battery = status.battery
        self.auto_off_countdown = status.countdown
        self.heater_mode = status.heater_mode
        self.heater = status.heater_mode != HEATER_MODE_OFF
        self.charging = status.charging
        bits = status.settings
        self.showing_celsius = not bits & BIT_FAHRENHEIT
        self.at_temperature = bool(bits & BIT_SETPOINT_REACHED)
        self.charge_optimization = bool(bits & BIT_CHARGE_OPTIMIZATION)
        self.target_changed_on_device = bool(bits & BIT_TARGET_CHANGED)
        self.charge_limit = bool(bits & BIT_CHARGE_LIMIT)
        visualization = bool(bits & BIT_BOOST_VISUALIZATION)
        self.boost_visualization = (
            not visualization if self.INVERT_BOOST_VISUALIZATION else visualization
        )
        if status.settings2 is not None:
            self.permanent_bluetooth = bool(status.settings2 & BIT2_PERMANENT_BLUETOOTH)

    def apply_firmware(self, firmware: QvapFirmware) -> None:
        """Take over a command-0x02 reply (spec §3.1)."""
        self.firmware_version = firmware.firmware_version
        self.bootloader_version = firmware.bootloader_version
        self.bootloader_mode = not firmware.application_running
        self.invalid_application = firmware.invalid_application
        self.invalid_bootloader = firmware.invalid_bootloader

    def apply_usage(self, usage: QvapUsage) -> None:
        """Take over a command-0x04 reply (spec §3.2)."""
        self.heat_time = usage.heater_minutes
        self.charging_time = usage.charging_minutes

    def apply_identity(self, identity: QvapIdentity) -> None:
        """Take over a command-0x05 reply (spec §3.3)."""
        self.serial_number = identity.serial
        if identity.color_index is not None:
            self.color = _COLOR_BY_INDEX.get(identity.color_index, "black")

    def apply_settings6(self, settings: QvapSettings) -> None:
        """Take over a command-0x06 reply (spec §3.4)."""
        self.brightness = settings.brightness
        self.vibration = settings.vibration
        self.boost_timeout_disabled = settings.boost_timeout_disabled


class VentyData(QvapData):
    """A Venty: permanent Bluetooth is read-only, no colour."""

    family = DeviceFamily.VENTY
    capabilities = _SHARED_CAPABILITIES | {VolcanoSensor.PERMANENT_BLUETOOTH_ENABLED}


class VeazyData(QvapData):
    """A Veazy: writable permanent Bluetooth, inverted visualisation bit, colour."""

    family = DeviceFamily.VEAZY
    INVERT_BOOST_VISUALIZATION = True
    capabilities = _SHARED_CAPABILITIES | {
        VolcanoSensor.PERMANENT_BLUETOOTH,
        VolcanoSensor.COLOR,
    }
```

- [ ] **Step 4: Run the data tests**

Register `VentyData`/`VeazyData` temporarily in `families.DATA_CLASSES` (as done for the Crafty in Task 6 Step 5), then: `RUN_TESTS tests/test_qvap_data.py -q` → PASS.

- [ ] **Step 5: `SimulatedQvap` in `tests/fakes.py`**

```python
class SimulatedQvap:
    """
    A Venty/Veazy behind a FakeBleakClient.

    Every write to the control characteristic is answered through the notify
    callback with the full reply for that command, the way the device does:
    a status write is applied to the state and answered with the new status.
    """

    def __init__(self, client: FakeBleakClient, *, veazy: bool = False) -> None:
        self.client = client
        self.veazy = veazy
        self.status = bytearray(
            [0x01, 0, 0x2E, 0x07, 0x44, 0x07, 10, 20, 85, 0x78, 0, 1, 0, 1, 0x02, 0, 0, 0, 0, 0]
        )
        self.firmware_flags = 0x01
        self.settings6 = bytearray([0x06, 0, 7, 0, 0, 1, 0])
        self.sent: list[bytes] = []
        client.write_gatt_char = self._write  # type: ignore[method-assign]

    async def _write(self, char: FakeCharacteristic, value: bytearray, response: bool = True) -> None:
        frame = bytes(value)
        self.client.written.append((char.uuid, frame))
        self.sent.append(frame)
        reply = self._reply(frame)
        if reply is not None and (callback := self.client.notify_callbacks.get(char.uuid)):
            await callback(char, bytearray(reply))

    def _reply(self, frame: bytes) -> bytes | None:
        cmd, mask = frame[0], frame[1]
        if cmd == 0x01:
            if mask & 0x02:
                self.status[4:6] = frame[4:6]
            if mask & 0x04:
                self.status[6] = frame[6]
            if mask & 0x08:
                self.status[7] = frame[7]
            if mask & 0x20:
                self.status[11] = frame[11]
            if mask & 0x80:
                self.status[14] = (self.status[14] & ~frame[15]) | (frame[14] & frame[15])
                self.status[16] = (self.status[16] & ~frame[17]) | (frame[16] & frame[17])
            return bytes(self.status)
        if cmd == 0x02:
            serial = b"VZ" if self.veazy else b"VY"
            return bytes([0x02, self.firmware_flags]) + b"V01.09" + bytes(3) + b"V00.05" + bytes(3)
        if cmd == 0x04:
            return bytes([0x04]) + (150).to_bytes(3, "little") + (40).to_bytes(3, "little") + bytes(13)
        if cmd == 0x05:
            reply = bytearray(20)
            reply[0] = 0x05
            reply[9:15] = b"654321" if self.veazy else b"123456"
            reply[15:17] = b"VZ" if self.veazy else b"VY"
            reply[18] = 3
            return bytes(reply)
        if cmd == 0x06:
            if mask & 0x01:
                self.settings6[2] = frame[2]
            if mask & 0x08:
                self.settings6[5] = frame[5]
            if mask & 0x10:
                self.settings6[6] = frame[6]
            return bytes(self.settings6)
        if cmd == 0x1D:
            return bytes([0x1D, 0x00])
        if cmd == 0x0D:
            return bytes([0x0D, 0x01])
        return None
```

(`serial` in the `0x02` branch is unused — drop that line; it is only there to keep the two prefixes next to each other. ruff will flag it, so do not copy it.)

- [ ] **Step 6: Protocol tests**

Create `tests/test_qvap_ble.py`:

```python
"""Tests for the Venty/Veazy protocol against a simulated device."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.volcano_hybrid.volcano_ble import qvap_frames as f
from custom_components.volcano_hybrid.volcano_ble.device import UnsupportedCommandError
from custom_components.volcano_hybrid.volcano_ble.qvap import (
    CHAR_CONTROL,
    CHAR_GAP_NAME,
    QvapDevice,
    VeazyDevice,
    VentyDevice,
)

from . import make_ble_device
from .fakes import FakeBleakClient, SimulatedQvap

ESTABLISH = "custom_components.volcano_hybrid.volcano_ble.device.establish_connection"


async def connect(*, veazy: bool = False) -> tuple[QvapDevice, SimulatedQvap]:
    client = FakeBleakClient({CHAR_GAP_NAME: b"S&B VY123456"})
    simulated = SimulatedQvap(client, veazy=veazy)
    device = (VeazyDevice if veazy else VentyDevice)(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)), patch.object(
        QvapDevice, "_start_polling"
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    return device, simulated


async def test_connect_runs_the_init_sequence_and_reads_everything() -> None:
    device, simulated = await connect()
    assert device.is_connected
    assert [frame[0] for frame in simulated.sent][:6] == [0x02, 0x1D, 0x01, 0x04, 0x05, 0x06]
    data = device.data
    assert data.firmware_version == "V01.09"
    assert data.bootloader_mode is False
    assert data.current_temp == 184
    assert data.set_temp == 186
    assert data.battery == 85
    assert data.heater is True
    assert data.serial_number == "VY123456"
    assert data.heat_time == 150
    assert data.brightness == 7
    assert data.find_mode is False


async def test_writes_are_confirmed_by_the_reply() -> None:
    device, simulated = await connect()
    simulated.sent.clear()

    assert await device.async_set_target_temperature(190)
    assert simulated.sent[0] == f.build_target_write(190)
    assert device.data.set_temp == 190
    assert not device.data.is_assumed

    assert await device.async_set_heater(False)
    assert simulated.sent[-1] == f.build_heater_write(False)
    assert device.data.heater is False

    assert await device.async_set_boost_temperature(12)
    assert device.data.boost_temp == 12
    assert await device.async_set_superboost_temperature(25)
    assert device.data.superboost_temp == 25


async def test_settings_writes() -> None:
    device, simulated = await connect()
    simulated.sent.clear()
    assert await device.async_set_charge_limit(True)
    assert simulated.sent[-1] == f.build_settings_write(f.BIT_CHARGE_LIMIT, f.BIT_CHARGE_LIMIT)
    assert device.data.charge_limit is True
    assert await device.async_set_showing_celsius(False)
    assert simulated.sent[-1] == f.build_settings_write(f.BIT_FAHRENHEIT, f.BIT_FAHRENHEIT)
    assert device.data.showing_celsius is False
    assert await device.async_set_brightness(3)
    assert simulated.sent[-1] == f.build_settings6_write(f.CMD6_BRIGHTNESS, brightness=3)
    assert device.data.brightness == 3
    assert await device.async_set_vibration(False)
    assert device.data.vibration is False
    assert await device.async_find_device()
    assert simulated.sent[-1] == f.build_find_device()


async def test_veazy_inverts_visualization_and_writes_permanent_bluetooth() -> None:
    device, simulated = await connect(veazy=True)
    simulated.sent.clear()
    assert await device.async_set_boost_visualization(True)
    assert simulated.sent[-1] == f.build_settings_write(0, f.BIT_BOOST_VISUALIZATION)
    assert device.data.boost_visualization is True
    assert await device.async_set_permanent_bluetooth(True)
    assert simulated.sent[-1] == f.build_settings_write(0, 0, f.BIT2_PERMANENT_BLUETOOTH, f.BIT2_PERMANENT_BLUETOOTH)
    assert device.data.permanent_bluetooth is True
    assert device.data.color == "pink"


async def test_venty_refuses_to_write_permanent_bluetooth() -> None:
    device, _ = await connect()
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_permanent_bluetooth(True)


async def test_bootloader_mode_blocks_control() -> None:
    """A device in its bootloader is reported, never driven (spec §3.1, §3.8)."""
    client = FakeBleakClient({CHAR_GAP_NAME: b"S&B VY123456"})
    simulated = SimulatedQvap(client)
    simulated.firmware_flags = 0x10
    device = VentyDevice(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)), patch.object(
        QvapDevice, "_start_polling"
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
    assert device.data.bootloader_mode is True
    # No 0x01 was sent after the firmware reply said "bootloader".
    assert 0x01 not in [frame[0] for frame in simulated.sent]
    with pytest.raises(UnsupportedCommandError):
        await device.async_set_heater(True)


async def test_forbidden_commands_are_never_sent() -> None:
    device, simulated = await connect()
    for cmd in f.FORBIDDEN_COMMANDS:
        with pytest.raises(UnsupportedCommandError):
            await device._async_write_frame(f.build_request(cmd))  # noqa: SLF001
    assert not any(frame[0] in f.FORBIDDEN_COMMANDS for frame in simulated.sent)


async def test_poll_once_sends_status_and_the_slow_commands() -> None:
    device, simulated = await connect()
    simulated.sent.clear()
    for _ in range(30):
        await device._async_poll_once()  # noqa: SLF001
    sent = [frame[0] for frame in simulated.sent]
    assert sent.count(0x01) == 30
    assert sent.count(0x04) == 1
    assert sent.count(0x06) == 1


async def test_poll_task_starts_and_stops_with_the_connection() -> None:
    client = FakeBleakClient({CHAR_GAP_NAME: b"S&B VY123456"})
    SimulatedQvap(client)
    device = VentyDevice(lambda: None, lambda: None)
    with patch(ESTABLISH, AsyncMock(return_value=client)), patch(
        "custom_components.volcano_hybrid.volcano_ble.qvap.QVAP_POLL_INTERVAL", 0
    ):
        await device.async_manual_update(make_ble_device(name="S&B VY123456"))
        assert device._poll_task is not None  # noqa: SLF001
        await asyncio.sleep(0)
        await device.async_disconnect()
    assert device._poll_task is None  # noqa: SLF001


async def test_pending_heater_write_is_dropped_when_off() -> None:
    device, simulated = await connect()
    simulated.status[11] = 0
    device.data.heater = False
    device.data.set_temp_write = 200
    await device._async_try_ensure_written_values()  # noqa: SLF001
    assert device.data.set_temp_write is None
```

- [ ] **Step 7: Create `volcano_ble/qvap.py`**

```python
"""Venty / Veazy protocol (VENTY_BLE_SPEC.md)."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakError

from . import qvap_frames as f
from .const import DeviceFamily
from .device import StorzBickelDevice, UnsupportedCommandError, _decode_ascii
from .qvap_data import QvapData, VeazyData, VentyData

_LOGGER = logging.getLogger(__name__)

SERVICE_UUID = "00000000-5354-4f52-5a26-4249434b454c"
CHAR_CONTROL = "00000001-5354-4f52-5a26-4249434b454c"
GAP_SERVICE_UUID = "00001800-0000-1000-8000-00805f9b34fb"
CHAR_GAP_NAME = "00002a00-0000-1000-8000-00805f9b34fb"

# The device does not push (spec §1.2): the vendor app polls every 500 ms.
# One second is plenty for Home Assistant and half the radio time.
QVAP_POLL_INTERVAL = 1.0
# The usage counters and the 0x06 settings barely move; the app refreshes the
# counters every ~15 s.
QVAP_SLOW_POLL_EVERY = 30
INIT_COMMANDS = (f.CMD_FIRMWARE, f.CMD_ADVERTISING, f.CMD_STATUS, f.CMD_USAGE, f.CMD_IDENTITY)


class QvapDevice(StorzBickelDevice):
    """A device speaking the Qvap frame protocol."""

    data: QvapData

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        """Initialize, with no poll task until connected."""
        super().__init__(*args, **kwargs)
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_tick = 0

    # -- connection --------------------------------------------------------

    async def _async_read_initial(self) -> None:
        client = self.client
        if client is None:
            return
        control = self._get_characteristic(client, SERVICE_UUID, CHAR_CONTROL)
        await client.start_notify(control, self._on_notify)
        await self._async_read_optional(GAP_SERVICE_UUID, CHAR_GAP_NAME, self._parse_gap_name)
        for cmd in INIT_COMMANDS:
            if cmd == f.CMD_STATUS and self.data.bootloader_mode:
                continue
            await self._async_write_frame(f.build_request(cmd))
        if not self.data.bootloader_mode:
            await self._async_write_frame(f.build_settings6_write(0))
        _LOGGER.debug("Initial %s frames read", self.family)
        self._after_data_updated()
        self._after_device_updated()
        self._start_polling()

    async def _async_refresh(self) -> None:
        if self.is_connected and not self.data.bootloader_mode:
            await self._async_write_frame(f.build_request(f.CMD_STATUS))

    def _on_disconnected(self) -> None:
        self._stop_polling()

    # -- polling -----------------------------------------------------------

    def _start_polling(self) -> None:
        if self._poll_task is None:
            self._poll_tick = 0
            self._poll_task = asyncio.create_task(self._async_poll_loop())

    def _stop_polling(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def _async_poll_loop(self) -> None:
        try:
            while self.is_connected:
                await asyncio.sleep(QVAP_POLL_INTERVAL)
                await self._async_poll_once()
        except asyncio.CancelledError:
            raise
        except BleakError as err:
            _LOGGER.debug("Polling %s failed, disconnecting: %s", self.family, err)
            self._poll_task = None
            await self.async_disconnect()

    async def _async_poll_once(self) -> None:
        """One poll: the status, and every 30th time the slow-moving values."""
        if self.data.bootloader_mode:
            return
        self._poll_tick += 1
        if self._poll_tick % QVAP_SLOW_POLL_EVERY == 0:
            await self._async_write_frame(f.build_request(f.CMD_USAGE))
            await self._async_write_frame(f.build_settings6_write(0))
        await self._async_write_frame(f.build_request(f.CMD_STATUS))

    # -- frames ------------------------------------------------------------

    async def _async_write_frame(self, frame: bytes) -> bool:
        """Send one frame, refusing anything that could touch the bootloader."""
        cmd = frame[0]
        if cmd in f.FORBIDDEN_COMMANDS or (cmd == f.CMD_STATUS and self.data.bootloader_mode):
            msg = f"command 0x{cmd:02x} is not sent to a device in its bootloader"
            raise UnsupportedCommandError(msg)
        return await self._write_gatt(SERVICE_UUID, CHAR_CONTROL, bytearray(frame))

    async def _on_notify(self, _: object, data: bytearray) -> None:
        frame = bytes(data)
        try:
            self._apply_frame(frame)
        except ValueError as err:
            _LOGGER.debug("Ignoring malformed %s frame %s: %s", self.family, frame.hex(), err)
            return
        self._after_data_updated()

    def _apply_frame(self, frame: bytes) -> None:
        if not frame:
            return
        cmd = frame[0]
        if cmd == f.CMD_STATUS:
            self.data.apply_status(f.parse_status(frame))
        elif cmd == f.CMD_FIRMWARE:
            self.data.apply_firmware(f.parse_firmware(frame))
            self._after_device_updated()
        elif cmd == f.CMD_USAGE:
            self.data.apply_usage(f.parse_usage(frame))
        elif cmd == f.CMD_IDENTITY:
            self.data.apply_identity(f.parse_identity(frame))
            self._after_device_updated()
        elif cmd == f.CMD_SETTINGS:
            self.data.apply_settings6(f.parse_settings6(frame))
        elif cmd == f.CMD_ADVERTISING:
            self.data.find_mode = f.parse_advertising(frame)
        else:
            _LOGGER.debug("Unhandled %s frame 0x%02x", self.family, cmd)

    def _parse_gap_name(self, data: bytearray) -> None:
        # "S&B VY123456": the serial is the second word (spec §1).
        parts = _decode_ascii(data).split(" ")
        if len(parts) > 1 and self.data.serial_number is None:
            self.data.serial_number = parts[1]

    # -- commands ----------------------------------------------------------

    def _require_application(self) -> None:
        if self.data.bootloader_mode:
            msg = "the device is in its bootloader"
            raise UnsupportedCommandError(msg)

    async def async_set_heater(self, on: bool) -> bool:
        """Switch between off and normal heating; the reply confirms."""
        self._require_application()
        self.data.heater_write = on
        written = await self._async_write_frame(f.build_heater_write(on))
        self._after_data_updated()
        return written

    async def async_set_target_temperature(self, target: float) -> bool:
        """Set the base target temperature."""
        self._require_application()
        self.data.set_temp_write = int(target)
        written = await self._async_write_frame(f.build_target_write(int(target)))
        self._after_data_updated()
        return written

    async def async_set_boost_temperature(self, offset: int) -> bool:
        """Set the boost offset."""
        self._require_application()
        return await self._async_write_frame(f.build_boost_write(offset))

    async def async_set_superboost_temperature(self, offset: int) -> bool:
        """Set the superboost offset."""
        self._require_application()
        return await self._async_write_frame(f.build_superboost_write(offset))

    async def _async_set_bit(self, bit: int, on: bool) -> bool:
        self._require_application()
        return await self._async_write_frame(f.build_settings_write(bit if on else 0, bit))

    async def async_set_showing_celsius(self, on: bool) -> bool:
        """Bit 0 is *Fahrenheit*."""
        return await self._async_set_bit(f.BIT_FAHRENHEIT, not on)

    async def async_set_charge_optimization(self, on: bool) -> bool:
        """Charge more slowly to spare the battery."""
        return await self._async_set_bit(f.BIT_CHARGE_OPTIMIZATION, on)

    async def async_set_charge_limit(self, on: bool) -> bool:
        """Stop charging short of 100 %."""
        return await self._async_set_bit(f.BIT_CHARGE_LIMIT, on)

    async def async_set_boost_visualization(self, on: bool) -> bool:
        """Show boost on the display; the Veazy stores the bit inverted."""
        return await self._async_set_bit(
            f.BIT_BOOST_VISUALIZATION, on != self.data.INVERT_BOOST_VISUALIZATION
        )

    async def async_set_permanent_bluetooth(self, on: bool) -> bool:
        """Only the Veazy branch of the vendor app writes this (spec §2.3)."""
        if self.family is not DeviceFamily.VEAZY:
            msg = "permanent Bluetooth is only written on a Veazy"
            raise UnsupportedCommandError(msg)
        self._require_application()
        bit = f.BIT2_PERMANENT_BLUETOOTH
        return await self._async_write_frame(f.build_settings_write(0, 0, bit if on else 0, bit))

    async def async_set_brightness(self, brightness: int) -> bool:
        """Display brightness 1-9."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_BRIGHTNESS, brightness=brightness)
        )

    async def async_set_vibration(self, on: bool) -> bool:
        """Vibration on or off."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_VIBRATION, vibration=on)
        )

    async def async_set_boost_timeout_disabled(self, on: bool) -> bool:
        """Whether boost never times out."""
        self._require_application()
        return await self._async_write_frame(
            f.build_settings6_write(f.CMD6_BOOST_TIMEOUT, timeout_disabled=on)
        )

    async def async_find_device(self) -> bool:
        """Make the device signal so it can be found."""
        self._require_application()
        return await self._async_write_frame(f.build_find_device())

    # -- pending writes ----------------------------------------------------

    async def _async_try_ensure_written_values(self) -> None:
        if (
            self.data.heater_needs_write or self.data.set_temp_needs_write
        ) and not self.data.is_on:
            self.data.clear_open_writes()
        if self.data.heater_needs_write and (on := self.data.heater_write) is not None:
            await self.async_set_heater(on)
        if (
            self.data.set_temp_needs_write
            and (target := self.data.set_temp_write) is not None
        ):
            await self.async_set_target_temperature(target)


class VentyDevice(QvapDevice):
    """A Venty."""

    family = DeviceFamily.VENTY
    data_class = VentyData


class VeazyDevice(QvapDevice):
    """A Veazy."""

    family = DeviceFamily.VEAZY
    data_class = VeazyData
```

Notes for the implementer:
- `StorzBickelDevice.__init__` has keyword-only `device`; the `*args, **kwargs` pass-through is fine for mypy because the base signature is known — if strict mypy complains, spell the parameters out.
- `_write_gatt` in the base uses `client.write_gatt_char(char, value)`; `SimulatedQvap._write` accepts the optional `response` keyword so a later switch to `response=True` does not break the fake.
- Register `DeviceFamily.VENTY: VentyDevice` and `DeviceFamily.VEAZY: VeazyDevice` in `families.DEVICE_CLASSES`; `DATA_CLASSES` is derived again.

- [ ] **Step 8: Run**

Run: `RUN_TESTS tests/test_qvap_ble.py tests/test_qvap_data.py tests/test_device.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/volcano_hybrid/volcano_ble tests
git commit -m "Speak the Venty and Veazy protocol"
```

---

### Task 11: Venty/Veazy entities, strings

**Files:**
- Modify: `sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `strings.json`, `translations/en.json`, `icons.json`
- Modify: `tests/test_entities_by_family.py`
- Test: `tests/test_qvap_entities.py` (new)

**Interfaces:**
- Consumes the Task 10 keys, `HEATER_MODE_OPTIONS`, `COLOR_OPTIONS`, `QvapData.heater_mode_name`; the coordinator commands from Task 8.
- Sensor `HEATER_MODE` reads `data.heater_mode_name` — use `value_fn` with the data-object variant: add a row-level `value_key: str | None` to `VolcanoSensorEntityDescription` (default `None`, meaning "same as key") so `HEATER_MODE` can read attribute `heater_mode_name`.

- [ ] **Step 1: Golden lists and the failing entity tests**

Add to `GOLDEN_ENTITIES`:

```python
    DeviceFamily.VENTY: {
        "climate": {"volcano"},
        "number": {"boost_temp", "superboost_temp", "brightness"},
        "switch": {
            "showing_celsius", "vibration", "charge_optimization", "charge_limit",
            "boost_visualization", "boost_timeout_disabled", "auto_connect",
        },
        "sensor": {
            "battery", "auto_off_countdown", "heater_mode", "heat_time",
            "charging_time", "rssi", "connected_addr",
        },
        "binary_sensor": {
            "at_temperature", "heater", "charging", "boost_mode", "superboost_mode",
            "target_changed_on_device", "bootloader_mode",
            "permanent_bluetooth_enabled", "connected",
        },
        "button": {"reconnect", "delayed_reconnect", "find_device"},
        "update": {"firmware"},
    },
```

and `DeviceFamily.VEAZY` identical except: `"switch"` adds `"permanent_bluetooth"`, `"sensor"` adds `"color"`, `"binary_sensor"` drops `"permanent_bluetooth_enabled"`.

Create `tests/test_qvap_entities.py`:

```python
"""Entity behaviour specific to the Venty/Veazy family."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON, STATE_OFF, STATE_ON

from custom_components.volcano_hybrid.volcano_ble import DeviceFamily

from . import FakeDevice, get_entity_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize("device_family", [DeviceFamily.VENTY], indirect=True, ids=str)
async def test_heater_mode_and_charging(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    mock_volcano.connected = True
    data = mock_volcano.data
    data.heater_mode = 3
    data.charging = True
    data.bootloader_mode = False
    data.permanent_bluetooth = True
    mock_volcano.data_updated()
    await hass.async_block_till_done()

    assert hass.states.get(get_entity_id(hass, "sensor", "heater_mode")).state == "superboost"
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "superboost_mode")).state == STATE_ON
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "charging")).state == STATE_ON
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "bootloader_mode")).state == STATE_OFF
    assert hass.states.get(get_entity_id(hass, "binary_sensor", "permanent_bluetooth_enabled")).state == STATE_ON


@pytest.mark.parametrize("device_family", [DeviceFamily.VEAZY], indirect=True, ids=str)
async def test_veazy_colour_and_permanent_bluetooth_switch(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
) -> None:
    mock_volcano.connected = True
    mock_volcano.data.color = "orange"
    mock_volcano.data.permanent_bluetooth = False
    mock_volcano.data_updated()
    await hass.async_block_till_done()
    assert hass.states.get(get_entity_id(hass, "sensor", "color")).state == "orange"
    entity_id = get_entity_id(hass, "switch", "permanent_bluetooth")
    assert hass.states.get(entity_id).state == STATE_OFF
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert ("permanent_bluetooth", True) in mock_volcano.commands


@pytest.mark.parametrize("device_family", [DeviceFamily.VENTY], indirect=True, ids=str)
@pytest.mark.parametrize(
    ("key", "value"), [("boost_temp", 12), ("superboost_temp", 25), ("brightness", 4)]
)
async def test_numbers(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
    value: int,
) -> None:
    entity_id = get_entity_id(hass, "number", key)
    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value}, blocking=True
    )
    assert (key, value) in mock_volcano.commands


@pytest.mark.parametrize("device_family", [DeviceFamily.VENTY], indirect=True, ids=str)
@pytest.mark.parametrize(
    "key",
    ["showing_celsius", "vibration", "charge_optimization", "charge_limit",
     "boost_visualization", "boost_timeout_disabled"],
)
async def test_switches(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    init_integration: MockConfigEntry,
    mock_volcano: FakeDevice,
    key: str,
) -> None:
    entity_id = get_entity_id(hass, "switch", key)
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert (key, True) in mock_volcano.commands
```

- [ ] **Step 2: Run to verify failure**

Run: `RUN_TESTS tests/test_entities_by_family.py tests/test_qvap_entities.py -q`
Expected: FAIL on the golden sets.

- [ ] **Step 3: Platform rows**

`number.py`: `SUPERBOOST_TEMP` like `BOOST_TEMP` (1–99 °C, config, box); `BRIGHTNESS` (config, slider, 1–9, step 1, no unit, disabled by default). Append both to `NUMBER_KEYS`.

`switch.py`: rows `CHARGE_OPTIMIZATION`, `CHARGE_LIMIT`, `BOOST_VISUALIZATION`, `BOOST_TIMEOUT_DISABLED`, `PERMANENT_BLUETOOTH` — config category, disabled by default (`PERMANENT_BLUETOOTH` enabled by default: it is the setting that decides whether the device is reachable). Append to `SWITCH_KEYS`. `SHOWING_CELSIUS` and `VIBRATION` are reused.

`sensor.py`: add `value_key: str | None = None` to `VolcanoSensorEntityDescription` and in `_handle_coordinator_update` read `self.coordinator.data.get(self.entity_description.value_key or self._key)`. Rows: `HEATER_MODE` (`SensorDeviceClass.ENUM`, `options=HEATER_MODE_OPTIONS`, `value_key="heater_mode_name"`, enabled), `CHARGING_TIME` (`DURATION`, minutes, `TOTAL_INCREASING`, suggested hours, diagnostic, disabled), `COLOR` (`ENUM`, `options=COLOR_OPTIONS`, diagnostic, disabled). Append to `SENSOR_KEYS`. Import `HEATER_MODE_OPTIONS`, `COLOR_OPTIONS` from `.volcano_ble.qvap_data`.

`binary_sensor.py`: rows `CHARGING` (`BATTERY_CHARGING`, enabled), `TARGET_CHANGED_ON_DEVICE` (diagnostic, disabled), `BOOTLOADER_MODE` (`PROBLEM`, diagnostic, enabled), `PERMANENT_BLUETOOTH_ENABLED` (diagnostic, disabled). Append to `BINARY_SENSOR_KEYS`.

- [ ] **Step 4: Strings and icons**

`strings.json` / `en.json` entity names: `number.superboost_temp` "Superboost temperature", `number.brightness` "Display brightness", `switch.charge_optimization` "Charge optimization", `switch.charge_limit` "Charge limit", `switch.boost_visualization` "Boost visualization", `switch.boost_timeout_disabled` "Boost timeout disabled", `switch.permanent_bluetooth` "Permanent Bluetooth", `sensor.heater_mode` "Heater mode" with `state` `{"off": "Off", "heating": "Heating", "boost": "Boost", "superboost": "Superboost"}`, `sensor.charging_time` "Total charging time", `sensor.color` "Colour" with `state` `{"black": "Black", "blue": "Blue", "pink": "Pink", "orange": "Orange"}`, `binary_sensor.charging` "Charging", `binary_sensor.target_changed_on_device` "Target changed on device", `binary_sensor.bootloader_mode` "Bootloader mode", `binary_sensor.permanent_bluetooth_enabled` "Permanent Bluetooth".

`icons.json`: `number.superboost_temp` `mdi:thermometer-high`, `number.brightness` `mdi:brightness-6`, `switch.charge_optimization` `mdi:battery-heart-variant`, `switch.charge_limit` `mdi:battery-80`, `switch.boost_visualization` `mdi:eye`, `switch.boost_timeout_disabled` `mdi:timer-off`, `switch.permanent_bluetooth` `mdi:bluetooth-connect`, `sensor.heater_mode` `mdi:fire`, `sensor.charging_time` `mdi:battery-clock`, `sensor.color` `mdi:palette`, `binary_sensor.target_changed_on_device` `mdi:gesture-tap-button`, `binary_sensor.bootloader_mode` `mdi:alert-decagram`, `binary_sensor.permanent_bluetooth_enabled` `mdi:bluetooth`.

- [ ] **Step 5: Run the suite**

Run: `RUN_TESTS`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A custom_components tests
git commit -m "Expose the Venty and Veazy as entities"
```

---

### Task 12: Per-family firmware tracking

**Files:**
- Modify: `custom_components/volcano_hybrid/firmware.py`, `update.py`, `scripts/check_firmware.py`, `.github/workflows/firmware-check.yml`
- Modify: `tests/test_firmware.py`, `tests/test_update.py`, `tests/test_check_firmware.py`

**Interfaces:**
- Produces `LATEST_KNOWN_FIRMWARE: Final[dict[str, tuple[int, int] | None]] = {"volcano_hybrid": (1, 3), "venty": None, "veazy": None}` (string keys so the script can `ast.literal_eval` it), `latest_firmware_version(family: DeviceFamily, installed) -> tuple[int, int] | None`.
- Script: `ENDPOINTS: dict[str, tuple[str, dict[str, str]]]` = `{"volcano_hybrid": (".../firmwareHybrid", {"version": "true"}), "venty": (".../firmware", {"device": "Venty", "action": "version", "serial": ""}), "veazy": (... "Veazy" ...)}`; `read_recorded_versions() -> dict[str, tuple[int, int] | None]`; `fetch_published_version(family)`; `main()` loops over the families, reports the first failure with status `f"{family}-{status}"`. Unknown recorded (`None`) plus a published version → status `outdated` with a body saying "record it once verified".

- [ ] **Step 1: Update the tests**

`tests/test_firmware.py`: `LATEST = LATEST_KNOWN_FIRMWARE["volcano_hybrid"]`; every `latest_firmware_version(x)` becomes `latest_firmware_version(DeviceFamily.VOLCANO_HYBRID, x)`; add:

```python
def test_latest_is_unknown_for_a_family_without_a_recorded_version() -> None:
    """Nothing is claimed for a Venty until somebody verifies a firmware."""
    assert latest_firmware_version(DeviceFamily.VENTY, (1, 9)) is None
```

`tests/test_update.py`: the Volcano tests use `LATEST_KNOWN_FIRMWARE["volcano_hybrid"]`; add a Venty test (parametrised `device_family`) asserting `latest_version` is `None` and `installed_version == "V01.09"` after `data.firmware_version = "V01.09"`.

`tests/test_check_firmware.py`: `_response` takes a `family` and builds the Hybrid shape or the Venty shape (`majorApplication`, `minorApplication`, `majorBootloader`, `minorBootloader`); `read_recorded_versions()` returns the dict; `_parse_response(raw)` unchanged; `build_outdated_report(family, recorded, published)` names the family; add `test_reports_unknown_recorded_version_as_outdated`.

- [ ] **Step 2: `firmware.py`**

```python
LATEST_KNOWN_FIRMWARE: Final[dict[str, tuple[int, int] | None]] = {
    "volcano_hybrid": (1, 3),
    # Nobody has verified a Venty or Veazy firmware against this integration
    # yet; None means the update entity reports no "latest" rather than
    # inventing one. The scheduled check still watches the vendor endpoint.
    "venty": None,
    "veazy": None,
}


def latest_firmware_version(
    family: DeviceFamily, installed: tuple[int, int] | None
) -> tuple[int, int] | None:
    """(docstring as today, plus:) Families without a recorded version report None."""
    if installed is None:
        return None
    known = LATEST_KNOWN_FIRMWARE.get(family.value)
    if known is None:
        return None
    return max(installed, known)
```

`update.py`: `latest_firmware_version(self.coordinator.family, self._installed)`; `_installed` falls back to `data.firmware` only when the data has that attribute (`getattr(data, "firmware", None)`).

- [ ] **Step 3: `scripts/check_firmware.py`**

- `ENDPOINTS` as in the interface block; `read_recorded_versions()` evaluates the dict literal and returns it; `fetch_published_version(family)` posts that family's body; `_parse_response` is unchanged (both endpoints return `majorApplication` / `minorApplication`).
- `build_outdated_report(family, recorded, published)`: title `f"{FAMILY_LABELS[family]} firmware {_format(published)} is available"`; when `recorded is None` the body says the integration records no version for this family yet and to add one after verifying; status stays `outdated`.
- `main()`: for each family, try/except `CheckError`, collect failures; write outputs for the first failure with `status=f"{family}-{failure.status}"`; return 1 if any.
- Workflow: the label creation already uses `${STATUS}`, so per-family statuses dedupe on their own; update the comment at the top of `firmware-check.yml` to mention the three families and extend the `paths:` list with nothing new (same two files).

- [ ] **Step 4: Run**

Run: `RUN_TESTS tests/test_firmware.py tests/test_update.py tests/test_check_firmware.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A custom_components scripts .github tests
git commit -m "Track the latest known firmware per device family"
```

---

### Task 13: Diagnostics for every family and the spec-traceability test

**Files:**
- Modify: `custom_components/volcano_hybrid/diagnostics.py`
- Modify: `tests/test_diagnostics.py`
- Test: `tests/test_spec_traceability.py` (new)

- [ ] **Step 1: Failing tests**

Append to `tests/test_diagnostics.py`:

```python
@pytest.mark.parametrize("device_family", [DeviceFamily.VENTY], indirect=True, ids=str)
async def test_diagnostics_for_a_venty(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_volcano: FakeDevice
) -> None:
    """Every field the family holds is dumped; the Volcano-only keys are absent."""
    mock_volcano.data.battery = 85
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diagnostics["entry_data"]["model"] == "venty"
    assert diagnostics["state"]["battery"] == 85
    assert diagnostics["state"]["heater_mode_name"] is None
    assert "registers" not in diagnostics
    assert "fan" not in diagnostics["state"]
```

Create `tests/test_spec_traceability.py`:

```python
"""Every UUID and mask in the new protocol modules must be in its spec document."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BLE = ROOT / "custom_components" / "volcano_hybrid" / "volcano_ble"
UUID_PREFIX = re.compile(r'"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"')
HEX_MASK = re.compile(r"= (0x[0-9A-Fa-f]{2,4})\b")


@pytest.mark.parametrize(
    ("module", "spec"),
    [
        ("crafty.py", "CRAFTY_BLE_SPEC.md"),
        ("crafty_data.py", "CRAFTY_BLE_SPEC.md"),
        ("qvap.py", "VENTY_BLE_SPEC.md"),
        ("qvap_frames.py", "VENTY_BLE_SPEC.md"),
    ],
)
def test_constants_are_documented(module: str, spec: str) -> None:
    source = (BLE / module).read_text(encoding="utf-8")
    document = (ROOT / spec).read_text(encoding="utf-8").lower()
    for prefix in UUID_PREFIX.findall(source):
        assert prefix in document, f"{module}: UUID {prefix} is not in {spec}"
    for mask in HEX_MASK.findall(source):
        # The spec writes 16-bit masks as 0x0010 and byte masks as 0x10.
        assert mask.lower() in document or f"0x{int(mask, 16):04x}" in document, (
            f"{module}: {mask} is not in {spec}"
        )
```

- [ ] **Step 2: Make diagnostics generic**

`diagnostics.py`: build `state` from the data object instead of a hand-written dict — every public attribute and property of `data` whose value is a `str | int | float | bool | None` (walk `type(data)` for properties via `inspect.getmembers`, plus `vars(data)` for plain attributes, skipping names starting with `_` and `device`, `capabilities`). Keep `entry_data`, `device` (serial, model_name, firmware fields via `getattr(..., None)`), `connection`; emit `registers` only when the data has a `prj1` attribute **and** `hist1` (the Volcano). `TO_REDACT` unchanged.

- [ ] **Step 3: Run**

Run: `RUN_TESTS tests/test_diagnostics.py tests/test_spec_traceability.py -q`
Expected: PASS. If a mask fails traceability, add the row to the spec (with its tag) — never delete the assertion.

- [ ] **Step 4: Commit**

```bash
git add custom_components/volcano_hybrid/diagnostics.py tests
git commit -m "Dump diagnostics for every family and tie the protocol constants to the specs"
```

---

### Task 14: Documentation and metadata

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `hacs.json`, `custom_components/volcano_hybrid/quality_scale.yaml`

- [ ] **Step 1: README**

- Title stays; first paragraph: "A Storz & Bickel integration for Home Assistant using Bluetooth: Volcano Hybrid, Crafty / Crafty+, Venty and Veazy."
- New section after *Installing*: **Supported devices** — a table with columns *Device*, *Tested on hardware*, *Notes*: Volcano Hybrid / yes / —; Crafty+ / **no** / "decoded from the vendor app; monitor-only below firmware V02.51"; Crafty / no / same; Venty / no / "polled every second while connected"; Veazy / no / same. Below it: "If you own one of the untested devices, please open an issue with the diagnostics download — that is how these become tested."
- *Usage*: keep the Volcano list; add a **Crafty / Crafty+** and a **Venty / Veazy** subsection each listing the entities from the golden lists in Tasks 8 and 11, one line each.
- New section **Sleeping devices** under *Connecting*: portable devices switch Bluetooth off when idle; their entities show *unavailable* until they wake and advertise; *Automatic Bluetooth shutdown* (Crafty) and *Permanent Bluetooth* (Veazy) change that at the cost of battery.
- *Troubleshooting*: the "not connected" heading loses "the Volcano Hybrid".
- Link the two new spec files next to the Volcano one.

- [ ] **Step 2: CHANGELOG `## [Unreleased]`**

```markdown
### Added

- Support for the Crafty and Crafty+ (experimental — decoded from the vendor
  web app and untested on hardware; see `CRAFTY_BLE_SPEC.md`).
- Support for the Venty and Veazy (experimental — untested on hardware; see
  `VENTY_BLE_SPEC.md`). These devices are polled once a second while connected.
- The integration is now titled "Storz & Bickel"; the domain and every
  existing entity id are unchanged.

### Changed

- Config entries record the device family (`model`); existing entries are
  migrated as Volcano Hybrids automatically.
```

- [ ] **Step 3: CLAUDE.md**

Rewrite the *Architecture* section: three spec files; `volcano_ble/` layout from the file-structure table of this plan; `TrackedValue` in place of the write/state pairs paragraph (semantics unchanged); capability filtering; the Qvap poll task; `families.py` as the registry to extend. Add a *Adding a device family* checklist: data class → device class → `families.py` → keys → platform rows → strings/icons → golden test → spec document.

- [ ] **Step 4: `hacs.json` and quality scale**

`hacs.json`: `"name": "Storz & Bickel (Volcano Hybrid, Crafty, Venty, Veazy)"`. `quality_scale.yaml`: comments that say "the vaporizer"/"Volcano Hybrid" where a family-neutral wording is now more accurate (`appropriate-polling`: mention the Venty poll task and why 1 s).

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md CLAUDE.md hacs.json custom_components/volcano_hybrid/quality_scale.yaml
git commit -m "Document the Crafty, Venty and Veazy support"
```

---

### Task 15: Full verification

- [ ] **Step 1: Lint and type-check on a clean clone in the container**

Run: `RUN_LINT`
Expected: ruff clean, mypy clean. Fix anything reported; typical culprits are `ANN` on the `SimulatedQvap` fake, `PLR0913` in tests (already ignored), and `TC` import placement.

- [ ] **Step 2: Coverage**

Run: `RUN_TESTS --cov=custom_components.volcano_hybrid --cov-report=term-missing`
Expected: total ≥ 95 %, `config_flow.py` 100 %. Add tests for any uncovered branch in the new device modules before moving on.

- [ ] **Step 3: Translation sync**

Run (any Python): a one-off `python -c "import json;a=json.load(open('custom_components/volcano_hybrid/strings.json'));b=json.load(open('custom_components/volcano_hybrid/translations/en.json'));assert a==b"`.
Expected: no assertion error.

- [ ] **Step 4: Hassfest locally**

Run the hassfest container per the *Validate CI skips branches* note (`docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest` or the action's image) — it validates the new `bluetooth` matchers and `manifest.json`.

- [ ] **Step 5: Commit any fixes and push the branch**

```bash
git add -A && git commit -m "Tidy after lint and coverage"
git push -u origin worktree-multi-device-support
```

Then hand over: per this repository's convention there are no PRs — ask before fast-forwarding `main`.
