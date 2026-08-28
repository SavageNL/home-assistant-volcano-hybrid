# Crafty / Crafty+ — BLE protocol specification

Everything known about how a Storz & Bickel **Crafty** and **Crafty+** talk over Bluetooth
Low Energy, written up the same way as [`VOLCANO_BLE_SPEC.md`](VOLCANO_BLE_SPEC.md) so the
two can be compared side by side. The Crafty is the closest relative of the Volcano Hybrid:
the same "one characteristic per value, uint16 little-endian, temperatures ×10" GATT style
and the same PRJSTAT status-word idea, on a different UUID base.

This is a **desk decode, not a live observation**. Nobody involved in this integration owns a
Crafty, so every claim is tagged with where it came from and nothing here has been checked
against a real device by this project.

| Tag | Meaning |
|---|---|
| **CONFIRMED** | Read from the vendor's own web app (`js/crafty.js` v3.4.1 from `app.storz-bickel.com`). The app is the only client Storz & Bickel ship, so what it does is what the device accepts. |
| **STRONG** | Consistent across the vendor app and at least one independent implementation (see §8), but only inferred — e.g. a value's meaning from how the app displays it. |
| **SPECULATIVE** | Plausible from naming or from another device; must be confirmed on hardware before anything depends on it. |

---

## 1. Transport

| | |
|---|---|
| Radio | Bluetooth LE, GATT server on the device |
| Advertised name | starts with `STORZ&BICKEL` (older firmware) or `Storz&Bickel` (newer) — CONFIRMED (the app's `namePrefix` filters) |
| Advertised services | `00000001-…`, `00000002-…`, `00000003-…` on the Crafty base (§1.1) — CONFIRMED (the app also filters on these) |
| Manufacturer ID | not used by the app for discovery. Whether the Crafty advertises `1736` like the Volcano is **SPECULATIVE**; do not rely on it |
| Connections | one central at a time (STRONG — same BLE module family as the Volcano) |
| Power | battery. The device switches Bluetooth off on its own after a while unless *auto BLE shutdown* (§4.2, PRJSTAT2 bit 12) is disabled — CONFIRMED that the setting exists and that the app warns it "causes faster battery drain" |

The last row is the important difference from the Volcano for a Home Assistant integration:
**a Crafty is mostly unreachable.** It only advertises when awake, and it goes back to
sleep. Reconnect logic has to tolerate long absences without treating them as errors.

### 1.1 UUID scheme

Every service and characteristic uses one 128-bit base:

```
xxxxxxxx-4c45-4b43-4942-265a524f5453
         ^^^^ ^^^^ ^^^^ ^^^^ ^^^^ ^^^^
         L E  K C  I B  & Z  R O  T S      ← ASCII "STORZ&BICKEL" written backwards
```

The leading 32 bits pick the characteristic; the last hex digit of those is the service it
lives in (`…1` → service 1, `…2` → service 2, `…3` → service 3). Throughout this document a
characteristic is named by those eight digits only.

Services (CONFIRMED):

| Service | Role |
|---|---|
| `00000001` | live control: temperatures, battery, heater, LED, auto-off |
| `00000002` | identity: serial, firmware versions |
| `00000003` | status words, lifetime counters, privileged writes |

---

## 2. Value encoding

Unless stated otherwise every value is a **uint16 little-endian** — the app reads
`byte0 + byte1*256` and writes `[value % 256, value / 256]` (CONFIRMED). Temperatures are
transmitted **×10** in °C (`1850` = 185.0 °C). Strings are UTF-8.

The vendor app assumes whole degrees when it writes (`Math.round(...)`, then `*10`). Whether
the device reports tenths is not known (SPECULATIVE either way); the Volcano never does.

---

## 3. Service `00000001` — control

| Char | Name | R/W/N | Encoding | Confidence |
|---|---|---|---|---|
| `00000011` | Current temperature | R, **notify** | uint16, °C ×10 | CONFIRMED |
| `00000021` | Target temperature | R/W | uint16, °C ×10. Range 40–210 °C (app clamps). See §3.1 for the Fahrenheit quirk | CONFIRMED |
| `00000031` | Boost temperature | R/W | uint16, °C ×10. An *offset* added to the target while boost is active; app clamps 1–99 and additionally to `target + boost ≤ 210` | CONFIRMED |
| `00000041` | Battery level | R, **notify** | uint16, percent | CONFIRMED |
| `00000051` | LED brightness | R/W | uint16, 0–100, app slider step 10 | CONFIRMED |
| `00000061` | Auto-off setting | R/W | uint16, **seconds**, 0–300. Write needs the security code first (§5.2) | CONFIRMED |
| `00000071` | Auto-off countdown | R, **notify** | uint16, seconds remaining until the heater switches off | CONFIRMED |
| `00000081` | Heater on | W | write two zero bytes (`00 00`) | CONFIRMED |
| `00000091` | Heater off | W | write two zero bytes (`00 00`) | CONFIRMED |

Characteristics `00000061`, `00000071`, `00000081`, `00000091` are **only touched on firmware
≥ V02.51** (§6). On older firmware the app does not resolve them; whether they exist on the
GATT server at all is unknown.

Unlike the Volcano, heater on/off carry no payload meaning (the Volcano writes `01`/`00`);
the Crafty app writes an `Int16 0` to whichever characteristic it wants. Whether the device
also accepts a single byte (storz-rs writes `[0x00]`) is SPECULATIVE.

### 3.1 The Fahrenheit quirk on the target temperature

When the app reads `00000021` it does `if (targetTemp > 210) targetTemp = (targetTemp-32)/1.8`
(CONFIRMED). That means: **a Crafty that is set to display Fahrenheit reports its target in
°F ×10** over the same characteristic. Any client must apply the same rule on read. Whether a
write is interpreted in the device's display unit or always as °C is not established
(SPECULATIVE — the app always writes what it believes is °C, but it also only ever writes
after reading, so it never exercises the case where the two disagree).

The Fahrenheit display setting itself is **not exposed over BLE** on the Crafty as far as the
app shows: the app toggles its own display unit locally (`clickOnTempLabel`) and never writes
anything for it. Compare the Venty, which has a unit bit (see `VENTY_BLE_SPEC.md`).

### 3.2 Setting the target rewrites the boost

The app's `writeSollTemperatureCrafty` writes `00000021` and then **immediately rewrites
`00000031` with the current boost value** (CONFIRMED). Why is not stated; the most likely
reason is that the firmware re-derives or clears the boost when the base target changes
(SPECULATIVE). A client that wants the boost preserved should do the same.

---

## 4. Service `00000003` — status words and privileged writes

| Char | Name | R/W/N | Encoding | Confidence |
|---|---|---|---|---|
| `00000093` | PRJSTAT1 (`prjStatusReg`) | R, **notify** | uint16 bit field, §4.1 | CONFIRMED |
| `000001c3` | PRJSTAT2 (`prjStatusReg2`) | R/W, **notify** | uint16 bit field, §4.2. Written as a whole word | CONFIRMED |
| `00000083` | System status (`systemStatusReg`) | R | uint16 bit field, §4.3 | CONFIRMED (≥ V02.51 only) |
| `00000063` | Battery status 1 (`akkuStatusReg`) | R | uint16 bit field, §4.3 | CONFIRMED (≥ V02.51 only) |
| `00000073` | Battery status 2 (`akkuStatusReg2`) | R | uint16 bit field, §4.3 | CONFIRMED (≥ V02.51 only) |
| `00000023` | Lifetime heating hours | R | uint16 | CONFIRMED |
| `000001e3` | Lifetime heating minutes | R | uint16, the minutes part | CONFIRMED (≥ V02.51 only; older firmware has hours only) |
| `000001b3` | Security code (`Sicherheitscode`) | W | uint16, §5.2 | CONFIRMED (≥ V02.51 only) |
| `000001d3` | Factory reset | W | single byte `00`, after security code `1000` | CONFIRMED (≥ V02.51 only) |

### 4.1 PRJSTAT1 — `00000093`

| Bit | Mask | Meaning | Confidence |
|---|---|---|---|
| 4 | `0x0010` | **Heater active** (`MASK_PRJSTAT_CRAFTY_ACTIVE`). Drives the app's "device on" state | CONFIRMED |
| 5 | `0x0020` | Boost mode enabled | CONFIRMED |
| 6 | `0x0040` | Superboost mode enabled | CONFIRMED |
| 3, 13 | `0x2008` | **Error** — the app flags `deviceHasErrors` and asks the user to contact support | CONFIRMED (that they are errors; not what they mean) |
| 15 | `0x8000` | "Please perform factory reset by pressing the power button for 10s" | CONFIRMED |

Boost and superboost are entered from the device's own button (double/triple press); the
app only *reads* bits 5/6. There is no BLE write that enables boost on the Crafty
(CONFIRMED by absence — the app has none). The effective target while boosted is `target +
boost` for boost and `target + boost + 15` for superboost (STRONG — the app's
`setShowSollTempMobile` uses a hard-coded `superBoostVal = 15` for the Crafty).

Everything the app knows about PRJSTAT1 is the five masks above; all other bits are
undecoded.

### 4.2 PRJSTAT2 — `000001c3`

Read on connect, subscribed, and **written back as a whole 16-bit word** after
read-modify-write (`projectRegister2ChangeBitC`, CONFIRMED). This differs from the Volcano's
"mask in the low half, value in the high half" register-write convention. The app re-reads
the register after every write to refresh its copy.

| Bit | Mask | Meaning | Polarity | Confidence |
|---|---|---|---|---|
| 0 | `0x0001` | Vibration **disabled** | 1 = off | CONFIRMED |
| 1 | `0x0002` | Charge LED **disabled** | 1 = off | CONFIRMED |
| 2 | `0x0004` | **Setpoint reached** | 1 = at temperature | CONFIRMED (read-only in practice) |
| 3 | `0x0008` | "Find my Crafty" — the device buzzes for 30 s | 1 = signalling; clears itself | CONFIRMED |
| 12 | `0x1000` | Automatic BLE shutdown enabled | 1 = device turns BT off when idle | CONFIRMED |

Bit 2 is the device's own "ready" signal, the equivalent of Volcano PRJSTAT1 bit 10. The app
colours the temperature green on it and shows the auto-off countdown only while it is set.
Whether it has the same re-arm hysteresis as the Volcano's bit is SPECULATIVE.

### 4.3 System and battery status words

Only read by the *Analysis* feature; none are subscribed. The app tests these masks
(CONFIRMED that the app tests them; the labels are the app's user-facing strings, so
STRONG for meaning):

| Word | Mask | App's message |
|---|---|---|
| Battery 1 | `0x4100` | "Please let the device cool down" |
| Battery 1 | `0x0003` | "Please charge the device" |
| Battery 1 | `0x0600` | contact support (error) |
| Battery 2 | `0x8000` | "Please use a different charger or cable" |
| System | `0x0200` | contact support (error) |
| System | `0x0280` | app sets `deviceHasErrors` on connect |

The support report the app builds lists, in order: serial, timestamp, PRJSTAT1, PRJSTAT2,
Battery 1, Battery 2, System — the same shape as the Volcano's five-register report, which is
why an integration should expose these raw as diagnostic sensors rather than decode them.

---

## 5. Service `00000002` — identity, and the privileged-write handshake

### 5.1 Identity

| Char | Name | Encoding | Confidence |
|---|---|---|---|
| `00000052` | Serial number | UTF-8; the app keeps the first 8 characters | CONFIRMED |
| `00000032` | Firmware version | UTF-8 string, e.g. `V02.51` — the app reads major from characters 1–2 and minor from the last two | CONFIRMED |
| `00000072` | BLE firmware version | **three raw bytes** `major, minor, patch`, shown as `V1.2.3` | CONFIRMED (≥ V02.51 only) |

### 5.2 Security code

Two writes are gated behind a "Sicherheitscode" written to `000001b3` immediately before
them (CONFIRMED):

| Code | Unlocks |
|---|---|
| `815` | writing the auto-off setting `00000061` |
| `1000` | writing the factory reset `000001d3` |

The code is a plain uint16 with no challenge; it is a guard against accidental writes, not
authentication. It is unknown whether it must precede *every* privileged write or arms the
device for a period (SPECULATIVE); the app writes it every time, so a client should too.

---

## 6. Firmware generations

The app branches on the firmware string (CONFIRMED):

| Condition | App behaviour |
|---|---|
| major ≤ 2 **and** minor < 51 (`oldCraftyFirmware`) | Settings tab hidden. Only reads: target, current, boost, serial, firmware string, PRJSTAT2, lifetime hours, LED brightness, battery, PRJSTAT1. **No heater on/off, no auto-off, no security code, no factory reset, no BLE version, no analysis.** |
| otherwise, major < 3 | Original Crafty on current firmware: everything except *factory reset* and *find my Crafty* |
| major ≥ 3 | **Crafty+**: everything |

So the model is inferred from the firmware version, not advertised. Note the heater cannot
be switched over BLE at all on the oldest firmware; such a device is monitor-only.

The firmware update path for the Crafty is not in the web app (the Volcano and Venty ones
are) — presumably it needs the desktop tool. Nothing about it is documented here.

---

## 7. What a client should read, and when

Mirrors the app's connect sequence (CONFIRMED), reordered by purpose:

| Subscribed (notify) | Read once per connection |
|---|---|
| current temperature `00000011`, battery `00000041`, auto-off countdown `00000071`, PRJSTAT1 `00000093`, PRJSTAT2 `000001c3` | target `00000021`, boost `00000031`, serial, firmware, BLE firmware, lifetime hours/minutes, LED brightness, auto-off setting, system/battery status words |

Derived values, all computed by the client:

| Value | Derivation | Confidence |
|---|---|---|
| Heater on | PRJSTAT1 bit 4 | CONFIRMED |
| Ready | PRJSTAT2 bit 2 | CONFIRMED |
| Effective target | target, `+ boost` in boost mode, `+ boost + 15` in superboost | STRONG |
| Session progress | countdown `00000071` / setting `00000061` | CONFIRMED (that is what the app's progress bar shows) |
| Lifetime heat time | `hours * 60 + minutes` | CONFIRMED |

The notes in `VOLCANO_BLE_SPEC.md` §5 (record a pending write *before* sending it; never
replay an on-command against a device that has since gone off; cold connects are slow) apply
unchanged — the Crafty pushes PRJSTAT1 on heater changes exactly like the Volcano, so the same
write-confirmation race exists (STRONG).

---

## 8. Sources

- **Vendor web app** — `js/crafty.js` and `js/main.js` from `https://app.storz-bickel.com/`,
  version 3.4.1 (fetched 2026-08-28). Ground truth for every CONFIRMED row: UUIDs, encodings,
  the bit masks (`MASK_PRJSTAT*` constants are the app's own names), the security codes, the
  firmware-version branching and the connect sequence.
- **[storz-rs](https://github.com/flakesonnix/storz-rs)** (`src/protocol/crafty.rs`) — Rust
  library with the same UUID table; its Crafty support is marked *untested on hardware* by
  its author. Agrees with the app everywhere it overlaps, except that it writes single-byte
  heater commands where the app writes two bytes.
- **[reactive-volcano-app](https://github.com/firsttris/reactive-volcano-app)**
  (`src/hooks/crafty/*`) — TypeScript web app; storz-rs was derived from it. Same table.
- **[J-Cat/crafty-control](https://github.com/J-Cat/crafty-control)** and
  **[ligi/VaporizerControl](https://github.com/ligi/VaporizerControl)** — older community
  clients for the original Crafty (pre-`V02.51` firmware era) using the same service 1/2
  characteristics; useful corroboration that the temperature/boost/battery/LED table has been
  stable since 2015.

No firmware image was decompiled for this document, so there is nothing here at the
STRONG-by-disassembly level that `VOLCANO_BLE_SPEC.md` has for the Volcano's registers.
Undecoded bits in PRJSTAT1/2 and the three status words are exactly that: undecoded.
