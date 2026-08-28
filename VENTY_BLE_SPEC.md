# Venty / Veazy — BLE protocol specification

Everything known about how a Storz & Bickel **Venty** and **Veazy** talk over Bluetooth Low
Energy. The vendor calls this protocol family *Qvap* in its code and the two devices share
it entirely; the few places they differ are called out. Written up the same way as
[`VOLCANO_BLE_SPEC.md`](VOLCANO_BLE_SPEC.md) and [`CRAFTY_BLE_SPEC.md`](CRAFTY_BLE_SPEC.md).

This is a **desk decode, not a live observation**. Nobody involved in this integration owns
either device; every claim carries a tag saying where it came from.

| Tag | Meaning |
|---|---|
| **CONFIRMED** | Read from the vendor's own web app (`js/qvap.js` v3.4.1 from `app.storz-bickel.com`), the only client Storz & Bickel ship. |
| **STRONG** | Consistent across the vendor app and an independent implementation that has been run against a real Venty (storz-rs, §9), or inferred from how the app displays a value. |
| **SPECULATIVE** | Plausible from naming or from a sibling device; must be confirmed on hardware before anything depends on it. |

---

## 1. Transport

| | |
|---|---|
| Radio | Bluetooth LE, GATT server on the device |
| Advertised name | `S&B VY<serial>` for a Venty, `S&B VZ<serial>` for a Veazy — CONFIRMED that the app detects the model by `includes("S&B VY")` / `includes("S&B VZ")`; the serial suffix is STRONG (the app takes `name.split(" ")[1]` as the serial, and cmd `0x05` returns the same `VY`/`VZ` prefix + six characters) |
| Advertised service | `00000000-5354-4f52-5a26-4249434b454c` — CONFIRMED (the app's discovery filter) |
| Manufacturer ID | not used by the app. Whether the advertisement carries `1736` is SPECULATIVE |
| Connections | one central at a time (STRONG) |
| Power | battery. Bluetooth is switched off when the device sleeps unless *permanent Bluetooth* (§5.4, settings2 bit 0) is enabled — CONFIRMED that the setting exists |

Like the Crafty, and unlike the Volcano, **a Venty is usually unreachable**: it advertises
only while awake. A Home Assistant integration has to treat long absences as normal.

### 1.1 One characteristic, framed commands

This is not a "one characteristic per value" GATT like the Volcano and Crafty. Everything
goes through a single characteristic (CONFIRMED):

| | UUID |
|---|---|
| Service | `00000000-5354-4f52-5a26-4249434b454c` (the same `STORZ&BICKEL` ASCII base as the Volcano) |
| Control characteristic | `00000001-5354-4f52-5a26-4249434b454c` — write + notify |
| Generic Access → Device Name | `00002a00-0000-1000-8000-00805f9b34fb`, read once for the serial (CONFIRMED; the app tolerates it being absent) |

The client **writes a frame** whose first byte is a command id; the device **notifies a frame
back** with the same command id in byte 0. Frames are 20 bytes for command `0x01` and most
others, 7 bytes for command `0x06` (CONFIRMED — the app allocates exactly those sizes). A
notify carries the *whole* state for that command, so a write of one field is answered with
a full status frame.

Writes use *write with response* when the browser supports it and plain `writeValue`
otherwise (CONFIRMED); storz-rs uses *write without response* against a real Venty and
works (STRONG that either is accepted).

### 1.2 The device does not push — the client polls

The vendor app sends command `0x01` (mask `0`) **every 500 ms** for as long as it is
connected, substituting command `0x04` every 31st tick (CONFIRMED — `periodicIntervalFunc`).
reactive-volcano-app does the same at 500 ms. Nothing observed shows the device notifying on
its own after the initial replies; treat unsolicited notifications as **SPECULATIVE** and
poll. This is the single biggest architectural difference from the Volcano for an
integration built around push.

---

## 2. Frame layout for command `0x01` — status

All multi-byte numbers are little-endian. Temperatures are °C ×10.

### 2.1 Notify (device → client), length ≥ 15 (17 with settings2)

| Byte | Meaning | Encoding | Confidence |
|---|---|---|---|
| 0 | command id `0x01` | | CONFIRMED |
| 1 | mask (echo; unused on read) | | CONFIRMED |
| 2–3 | **Current temperature** | uint16, °C ×10 | CONFIRMED (the app's `updateCurrTemperatureMobile((b2 + b3*256)/10)`). storz-rs labels these bytes "UNUSED" and reactive-volcano-app ignores them; the vendor app is right |
| 4–5 | **Target temperature** | uint16, °C ×10; 40–210 °C | CONFIRMED |
| 6 | **Boost offset** | uint8, °C, added to the target in boost mode; app clamps 1–99 | CONFIRMED |
| 7 | **Superboost offset** | uint8, °C; app clamps 1–99 | CONFIRMED |
| 8 | **Battery level** | uint8, percent | CONFIRMED |
| 9–10 | **Auto-off countdown** | seconds. The app adds the two bytes (`b9 + b10`) and draws a bar out of 120 s; storz-rs reads uint16 LE. The two agree while `b10 = 0`, which is always the case if the countdown never exceeds 255 s. Read it as **uint16 LE** (STRONG); the full countdown is **120 s** (STRONG — the app's bar) |
| 11 | **Heater mode** | `0` off, `1` heating, `2` boost, `3` superboost | CONFIRMED |
| 12 | unknown | | — |
| 13 | **Charger connected** | `> 0` = charging | CONFIRMED |
| 14 | **Settings** bit field, §2.3 | | CONFIRMED |
| 15 | settings write-mask (echo) | | CONFIRMED |
| 16 | **Settings2** bit field, §2.3 | only present when length ≥ 17 | CONFIRMED |
| 17 | settings2 write-mask (echo) | | CONFIRMED |
| 18–19 | unknown | | — |

### 2.2 Write (client → device)

Byte 1 selects which fields the device should take from the frame; the rest is the same
layout. Everything not selected by the mask is ignored (CONFIRMED — the app leaves the rest
zero).

| Mask bit | Value | Fields applied | Confidence |
|---|---|---|---|
| 1 | `0x02` | target temperature, bytes 4–5 | CONFIRMED |
| 2 | `0x04` | boost offset, byte 6 | CONFIRMED |
| 3 | `0x08` | superboost offset, byte 7 | CONFIRMED |
| 4 | `0x10` | auto-off countdown, bytes 9–10 | **SPECULATIVE** — storz-rs and reactive-volcano-app send it; the vendor app's `writeAutoOffCountdownQVap` is an empty stub, so the vendor never writes it |
| 5 | `0x20` | heater mode, byte 11 | CONFIRMED for `0` and `1`. The app only ever toggles between off and `1`; writing `2`/`3` to enter boost is SPECULATIVE (storz-rs offers it, untested) |
| 7 | `0x80` | settings: byte 14 = new bit values, byte 15 = which bits; settings2: byte 16 = values, byte 17 = which bits | CONFIRMED |

Bits 0 and 6 of the mask are unused by every known client.

A settings write is therefore a masked update: to enable *charge optimisation* the app sends
`byte14 = 0x08, byte15 = 0x08`; to disable it `byte14 = 0x00, byte15 = 0x08` (CONFIRMED).

### 2.3 Settings bits (byte 14) and settings2 bits (byte 16)

| Byte | Bit | Mask | Meaning | Confidence |
|---|---|---|---|---|
| 14 | 0 | `0x01` | Display unit: `1` = Fahrenheit, `0` = Celsius. Temperatures over BLE stay in °C regardless (CONFIRMED — the app converts for display only) | CONFIRMED |
| 14 | 1 | `0x02` | **Setpoint reached** (read-only) | CONFIRMED |
| 14 | 2 | `0x04` | Factory reset (write `1` with mask `0x04`; the app then rereads and shows 180 °C as the target) | CONFIRMED |
| 14 | 3 | `0x08` | Charge optimisation ("ecomode charge": slower charging, longer battery life) | CONFIRMED |
| 14 | 4 | `0x10` | **Target changed on the device** — the app only accepts a new target from the frame when this is set (or on first read), so it means the buttons moved the setpoint since the last write | STRONG |
| 14 | 5 | `0x20` | Charge limit ("ecomode voltage": stops short of 100 %, longer battery life) | CONFIRMED |
| 14 | 6 | `0x40` | Boost/superboost visualisation on the display. **Inverted on the Veazy**: `1` = off there | CONFIRMED |
| 16 | 0 | `0x01` | Permanent Bluetooth (device keeps BT on while asleep). Only the Veazy branch of the app writes it; both read it | CONFIRMED |

reactive-volcano-app and storz-rs treat bit 6 as also meaning *vibration*. The vendor app
does not: vibration is a command `0x06` field (§5.1). Trust the vendor.

---

## 3. Other commands

Every request is a 20-byte frame with just byte 0 set unless noted; the device answers with
a frame of the same id.

### 3.1 `0x02` — firmware info

Reply length ≥ 19 (CONFIRMED):

| Byte | Meaning |
|---|---|
| 1 | Application flags: bit 0 `0x01` = application running (else the device is in its **bootloader**), bit 4 `0x10` = invalid application, bit 5 `0x20` = invalid bootloader |
| 2–7 | **Firmware version, UTF-8**, six characters (e.g. `V01.09`). The app parses `(\d+)\.?(\d+)$` out of it for major/minor |
| 8–10 | unknown |
| 11–16 | **Bootloader version, UTF-8**, six characters |

storz-rs and reactive-volcano-app decode bytes 1–4 and 5–8 as four raw version bytes
each. That disagrees with the vendor app, which decodes strings at offsets 2 and 11, and the
regex it applies would not work on raw bytes. The vendor decode is CONFIRMED; the community
decode is wrong.

Bit 0 of byte 1 clear means *the device is sitting in the bootloader*, which happens after
an interrupted update or when the user holds the buttons to enter it. The app then prompts
for a firmware update. A client that is not going to flash should recognise this state and
report it, not try to control the device (heating commands are meaningless there).

### 3.2 `0x04` — usage counters

Reply length ≥ 20: bytes 1–3 = **heater runtime in minutes** (uint24 LE), bytes 4–6 =
**battery charging time in minutes** (uint24 LE). CONFIRMED.

### 3.3 `0x05` — serial and colour

Reply length > 17: bytes 15–16 = two-character prefix (`VY` / `VZ`), bytes 9–14 = six
characters; the app concatenates them as the serial (CONFIRMED). Byte 18 (when present) =
**colour index**, decoded by the app only for the Veazy: `2` blue, `3` pink, `4` orange,
anything else black (CONFIRMED).

### 3.4 `0x06` — brightness, vibration, boost timeout (7-byte frame)

Request: `[0x06, mask, b2, 0, 0, b5, b6]`. Reply has the same layout (CONFIRMED):

| Mask bit | Byte | Meaning | Confidence |
|---|---|---|---|
| 0 (`0x01`) | 2 | Display brightness, **1–9** | CONFIRMED |
| 3 (`0x08`) | 5 | Vibration, `0`/`1` | CONFIRMED |
| 4 (`0x10`) | 6 | Boost/superboost **timeout disabled**, `0`/`1` (`1` = the boost never times out). Only offered on Venty firmware minor ≥ 8, always on the Veazy | CONFIRMED |

storz-rs calls byte 6 "boost timeout in seconds"; the vendor app writes a boolean and labels
it *timeout disabled*. Trust the vendor.

Reading all three: send `[0x06, 0, 0, 0, 0, 0, 0]`.

### 3.5 `0x0D` — find my device

`[0x0D, 0x01, …]` makes the device signal so it can be found (CONFIRMED). The reply has
the same id. Whether it is in find-mode is reported through `0x1D`.

### 3.6 `0x1D` — advertising info

Reply byte 1 bit 4 (`0x10`) = find-my-device mode active (CONFIRMED). Sent once on connect.

### 3.7 `0x03` / `0x23` — analysis

`0x03` runs the device's self-analysis; reply bytes 1 = error code, 2 = error category
(`4` = a fault was found and the app suggests an RMA) (CONFIRMED). `0x23` fetches a signing
key id used to upload the analysis dump; `0x00` with byte 1 = `3` / `8` streams 16 × 16-byte
pages of that dump. All of this exists to send data to Storz & Bickel's server and is of no
use to an offline client; documented so nobody mistakes the frames for something else.

### 3.8 Commands that must never be sent

| Frame | Effect |
|---|---|
| `[0x0C, 0x66, 0x33]` | **Switches the device into its bootloader** and disconnects. The application only starts again after a successful flash or a button press |
| `[0x01 or 0x30, 0x01..0x08, …]` | Bootloader page-write / erase / validate / start-application sequence (`0x30` prefix when updating the bootloader itself, `0x01` for the application) |
| `[0x01 or 0x30, 0x05, chunk]` | Bootloader chunk-size negotiation |
| `[0x01 or 0x30, 0x06]` | Connection-interval query — harmless by itself, but part of the update flow |

All CONFIRMED. The flashing protocol (2048-byte pages, 128-byte data packets, per-page IV,
status codes `1` next packet / `2` page done / `8` decrypt done / `0x13`, `0x22`, `0x23`,
`0x33`, `0x52`, `0x62` failures) is documented here only so that it is recognisable; see
`VOLCANO_BLE_SPEC.md` §6.2 for why this integration does not flash firmware. Note that the
Venty application-mode command `0x01` and the bootloader's page-data sub-command share an id
and are told apart by the device's mode and by byte 1 — one more reason not to write mask
values this document does not list.

---

## 4. Connect sequence

What the vendor app does after `startNotifications()` on the control characteristic
(CONFIRMED, in order):

1. read GAP device name → serial (optional)
2. `0x02` firmware info (with response)
3. `0x1D` advertising info
4. `0x01` status
5. `0x04` usage counters
6. `0x23` key id (only if the application is running; `0x03` in the bootloader)
7. `0x05` serial and colour
8. `0x06` brightness / vibration / boost timeout (7 bytes)
9. `[0x01, 0x06]` connection interval (`0x30` prefix in the bootloader)
10. every 500 ms: `0x01`; every 31st tick `0x04` instead

storz-rs, verified on a real Venty, gets away with just steps 2, 3, 4, 5 — so the minimum a
client needs is `0x02, 0x1D, 0x01, 0x04` (STRONG). Whether `0x1D` is required at all is
SPECULATIVE. A client should skip 6 and 9.

---

## 5. Model differences and limits

| | Venty | Veazy |
|---|---|---|
| Name prefix | `S&B VY` | `S&B VZ` |
| Boost visualisation bit | direct | **inverted** |
| Permanent Bluetooth | read | read + write |
| Boost timeout toggle | firmware minor ≥ 8 | always |
| Colour index (`0x05` byte 18) | ignored | decoded |

Limits used by the app (CONFIRMED): target 40–210 °C, boost and superboost offsets 1–99 °C,
brightness 1–9. The **effective** target in boost mode is `target + boost` (STRONG —
reactive-volcano-app; the vendor app's own arithmetic for the Venty is inconsistent). What
superboost adds — `superboost` alone, or `boost + superboost` — is SPECULATIVE; the two
community projects disagree with the vendor app's arithmetic and with each other. Report the
three raw values and the mode rather than a computed effective temperature until this is
observed.

---

## 6. What a client should read, and when

| On connect | Poll while connected | Derived |
|---|---|---|
| `0x02`, `0x05`, `0x04`, `0x06`, `0x1D` | `0x01` every 500 ms–2 s; `0x04` and `0x06` occasionally (the app: `0x04` every ~15 s) | heater on = mode ≠ 0; ready = settings bit 1; charging = byte 13 > 0; effective target per §5 |

Because every `0x01` reply carries the full state, a *pending write* is confirmed by the
very next poll reply — there is no per-value notification to race against (contrast
`VOLCANO_BLE_SPEC.md` §5). The rule about never replaying an "on" command against a device
that has since gone off still applies; so does treating bootloader mode (§3.1) as
"do not control".

---

## 7. Unknowns, and how to settle them

1. Whether the device notifies `0x01` on its own (§1.2). Connect, send the init sequence, stop
   polling, change the temperature on the device: does a frame arrive?
2. Mask `0x10` (auto-off countdown write) and heater modes `2`/`3` over BLE (§2.2).
3. What superboost adds to the target (§5). Read `0x01` in each mode with known offsets.
4. Frame bytes 12, 18, 19 of `0x01`, and 8–10 of `0x02`.
5. Whether the advertisement carries manufacturer id `1736` (§1) — decides whether a
   Bluetooth matcher can use it.

---

## 8. Sources

- **Vendor web app** — `js/qvap.js` and `js/main.js` from `https://app.storz-bickel.com/`,
  version 3.4.1 (fetched 2026-08-28). Ground truth for every CONFIRMED row; the bit names
  (`BIT_SETTINGS_*`, `maskSetTemperatureWrite`, …) are the app's own.
- **[storz-rs](https://github.com/flakesonnix/storz-rs)** (`src/protocol/venty.rs`) — Rust
  library, **verified on a real Venty** by its author; source of the STRONG rows about the
  minimal init sequence and write-without-response. Disagrees with the vendor app on the
  `0x02` decode, the current-temperature bytes and the meaning of settings bit 6 and `0x06`
  byte 6; the vendor app wins on each.
- **[reactive-volcano-app](https://github.com/firsttris/reactive-volcano-app)**
  (`src/hooks/venty-veazy/*`) — TypeScript web app storz-rs was derived from; same
  agreements and disagreements.
