# Volcano Hybrid — BLE protocol specification

Everything this integration knows about how a Storz & Bickel Volcano Hybrid talks over
Bluetooth Low Energy: the services, every characteristic, how each value is encoded, and
what the status registers mean bit by bit. It also documents the firmware-update
(bootloader) protocol, which this integration deliberately does **not** implement.

This is reference documentation, not a promise: it describes a device nobody published a
specification for. Every claim is tagged with where it came from.

| Tag | Meaning |
|---|---|
| **CONFIRMED** | Read from the vendor's own web app (`js/volcano.js`, ground truth for the BLE layer) and/or observed live on a device. |
| **STRONG** | Derived from a Ghidra decompile of the V01.03 application firmware (STM32F072). Consistent, but not observed live. |
| **SPECULATIVE** | Plausible from firmware structure or naming. Must be confirmed empirically before anything depends on it. |

Live observations were made against a Volcano Hybrid running firmware **V01.03**
(`V01.03.00.0022`).

---

## 1. Transport

| | |
|---|---|
| Radio | Bluetooth LE, GATT server on the device |
| Advertised name | contains `VOLCANO H` (e.g. `S&B VOLCANO H 123456`) |
| Manufacturer ID | `1736` (`0x06C8`, Storz & Bickel) |
| Advertising interval | roughly every 10 s while idle |
| Connections | one central at a time |

Two facts drive most of the integration's design:

- **A connected Volcano stops advertising.** Home Assistant therefore has no `BLEDevice`
  for it while connected, and address lookups return `None`. Nothing may gate polling or
  reconnection on seeing an advertisement.
- **Holding the connection locks everyone else out**, including the official app. That is
  why the integration exposes an *Auto connect* switch and a delayed-reconnect button.

### Architecture behind the GATT

The GATT server is served by a **separate BLE module**; the STM32F072 main controller
talks to that module over USART1 (STRONG — peripheral map in the firmware decompile). The
status registers below are the controller's status words as forwarded to the module,
which is why they read like internal firmware state rather than a designed API.

### UUID scheme

Every characteristic uses the same 128-bit base:

```
xxxxxxxx-5354-4f52-5a26-4249434b454c
         ^^^^ ^^^^ ^^^^ ^^^^ ^^^^ ^^^^
         S T  O R  Z &  B I  C K  E L      ← ASCII "STORZ&BICKEL"
```

The leading 32 bits select service and characteristic: `1011xxxx` is the control service,
`1010xxxx` the status/identity service. Throughout this document a characteristic is
named by those eight digits only (`10110001` means
`10110001-5354-4f52-5a26-4249434b454c`).

The firmware-update service is the one exception and uses an unrelated base
(`00000002-1989-0108-1234-123456789abc`, see §6).

---

## 2. Service `10110000` — control and settings

All multi-byte values are **little-endian**. Temperatures are in **tenths of a degree
Celsius** (`1900` = 190.0 °C); the device only ever reports whole degrees, so the tenths
digit is always `0`.

| Characteristic | Used as | Encoding | Notes |
|---|---|---|---|
| `10110001` | Current temperature | `uint16`, deci-°C | Read + **notify**. Only notifies on change. CONFIRMED |
| `10110003` | Target temperature | `uint16`, deci-°C | Read/write + **notify**. Writable range 40–230 °C. CONFIRMED |
| `10110005` | LED brightness | `uint16`, percent 0–100 | Read/write. CONFIRMED |
| `1011000c` | Auto-off countdown | `uint16`, seconds remaining | Read + **notify**. Counts down while the device is on; `0` when not running. CONFIRMED |
| `1011000d` | Auto-off setting | `uint16`, seconds | Read/write. The UI offers 0–360 min in 30-min steps. CONFIRMED |
| `1011000f` | Heater **on** | write 1 byte (`0x01`) | Command characteristic. CONFIRMED |
| `10110010` | Heater **off** | write 1 byte (`0x00`) | Command characteristic. CONFIRMED |
| `10110013` | Pump/fan **on** | write 1 byte (`0x01`) | Command characteristic. CONFIRMED |
| `10110014` | Pump/fan **off** | write 1 byte (`0x00`) | Command characteristic. CONFIRMED |
| `10110015` | Lifetime heater hours | `uint16`, hours | Read + **notify**. CONFIRMED |
| `10110016` | Lifetime heater minutes | `uint16`, minutes | Read + **notify**. Combine as `hours * 60 + minutes`. CONFIRMED |

**On/off are four separate characteristics, not two writable flags.** The action is
selected by *which* characteristic is written; the payload byte carries no information
(this integration writes `0x01` to the on characteristics and `0x00` to the off ones,
mirroring the vendor app). There is no "toggle" and no combined state characteristic —
the resulting state is observed through PRJSTAT1 (§3).

Writes are **not acknowledged with the resulting state**. The device confirms a command by
pushing a PRJSTAT1 (or target-temperature) notification, which can arrive *before* the
write call returns — see §5.

---

## 3. Service `10100000` — status, identity and history

| Characteristic | Used as | Encoding | Notes |
|---|---|---|---|
| `10100001` | Bootloader version | ASCII string | Contains `BL` while the device sits in bootloader mode — that is how a half-finished flash is detectable. CONFIRMED |
| `10100003` | Firmware string | ASCII string | A second version/identity string. This integration only uses it as a fallback when `10100005` is empty. Exact meaning unconfirmed. SPECULATIVE |
| `10100004` | BLE-module firmware version | ASCII string | The version of the BLE module, not the main controller. CONFIRMED |
| `10100005` | Firmware version | ASCII string, e.g. `V01.03` | The application firmware of the main controller. This is the version that tracks Storz & Bickel's published releases. CONFIRMED |
| `10100008` | Serial number | ASCII string, space-padded | CONFIRMED |
| `1010000c` | **PRJSTAT1** | `uint16` bit field | Read + **notify**. Live device state: heater, pump, ready, faults. §3.1 |
| `1010000d` | **PRJSTAT2** | `uint16` bit field | Read + **notify** + write (see §3.4). Display settings and a second error group. §3.2 |
| `1010000e` | **PRJSTAT3** | `uint16` bit field | Read + **notify** + write (see §3.4). Vibration setting. §3.3 |
| `10100011` | Code number | `uint16` write | Writing `4711` unlocks entry into the bootloader. Not touched by this integration. CONFIRMED (vendor app) |
| `10100015` | **HIST1** | 8 bytes, opaque | Status-word snapshot captured at the last fault. §3.5 |
| `10100016` | **HIST2** | 8 bytes, opaque | Second fault snapshot. §3.5 |

### 3.1 PRJSTAT1 — `1010000c`

The one register that matters for live state. It is a notify characteristic, so every
change is pushed.

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 0 | `0x0001` | Heater running | CONFIRMED (live) |
| 1 | `0x0002` | Heater running (companion bit, tracks bit 0) | CONFIRMED (live) |
| 3 | `0x0008` | Error bit A — cause unknown | error CONFIRMED, cause SPECULATIVE |
| 4 | `0x0010` | **Actuator feedback fault** — heater or pump did not reach the state it was commanded into | STRONG |
| 5 | `0x0020` | Heater enabled (`HEIZUNG_ENA`) — the heater switch state | CONFIRMED |
| 9 | `0x0200` | Auto-BLE-shutdown armed | CONFIRMED (live) |
| 10 | `0x0400` | **Setpoint reached** — the device is at temperature | CONFIRMED (live) |
| 13 | `0x2000` | Pump/fan FET enabled (`PUMPE_FET_ENABLE`) — the fan switch state | CONFIRMED |
| 14 | `0x4000` | Error bit C — cause unknown | error STRONG, cause SPECULATIVE |
| — | `0x4018` | `ERR` — the OR of bits 3, 4 and 14; any of them means "the device reports a fault" | CONFIRMED |

Bit 4 is the only error bit whose cause is known. It is set by the firmware's
post-actuation check: after switching the heater or the pump, the controller verifies the
actuator actually responded, and flags this bit when it did not (STRONG — from
`FUN_08001fbc` calling the `FUN_08007938`/`FUN_08007930` checks). Bits 3 and 14 are
deliberately left undecoded rather than guessed; §7 explains how to pin them down.

**Bit 5 vs bits 0/1.** Bit 5 is the heater *switch*: it is set the moment the heater is
turned on and stays set until it is turned off. Bits 0 and 1 track the heater actually
running. In practice they move together.

**The three-state observation** that established bit 10, taken on one device across a full
heat cycle with a 40 °C setpoint:

| | Off / cold | Heating, 31 °C (below target) | At target, 40 °C |
|---|:--:|:--:|:--:|
| PRJSTAT1 | `0x0000` | `0x0023` | `0x0623` |
| bit 10 `0x0400` (reached) | 0 | 0 | **1** |
| bit 9 `0x0200` (auto shutdown) | 0 | 0 | **1** |
| bits 0, 1, 5 (heater) | 0 | 1 | 1 |

`0x0623 ^ 0x0023 = 0x0600`: exactly bits 9 and 10 flip on reaching temperature. This also
corrected an earlier assumption — **the auto-shutdown bit arms when the setpoint is
reached, not when heating starts**, so it is not a usable "heating" signal.

### 3.2 PRJSTAT2 — `1010000d`

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 0, 1, 3, 4, 5 | `0x003b` | `ERR` — the OR of these bits is a second fault group; the individual bits are unknown | error CONFIRMED, individual bits SPECULATIVE |
| 9 | `0x0200` | Display in Fahrenheit (**0 means Celsius**) | CONFIRMED |
| 12 | `0x1000` | Display stays on while cooling (**0 means enabled**) | CONFIRMED |

Note the inverted polarity of bits 9 and 12: the clear bit is the enabled state.

### 3.3 PRJSTAT3 — `1010000e`

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 10 | `0x0400` | Vibration (**0 means enabled**) | CONFIRMED |
| 12 | `0x1000` | Appears only at the setpoint (`0x0467` → `0x1467`), corroborating PRJSTAT1 bit 10 | SPECULATIVE |

PRJSTAT1 bit 10 is preferred over this bit for "ready" because PRJSTAT1 is the register the
device pushes on change.

### 3.4 Writing settings bits (PRJSTAT2 / PRJSTAT3)

Settings held in PRJSTAT2 and PRJSTAT3 are changed by writing a **4-byte little-endian
word** to the register characteristic — not by writing the whole register back:

| Write | Effect |
|---|---|
| `mask` | **set** the bits in `mask` |
| `0x10000 + mask` | **clear** the bits in `mask` |

So `0x00000200` sets the Fahrenheit bit and `0x00010200` clears it. Bit 16 of the written
word is the set/clear selector; the low 16 bits are the mask. CONFIRMED (vendor app; this
is what the integration's Celsius, display-on-cooling and vibration switches do).

PRJSTAT1 is not written this way — the heater and pump have their own command
characteristics (§2).

### 3.5 HIST1 / HIST2 — `10100015` / `10100016`

These are **not** error codes. On entering an error state the firmware copies a 3 × 16-bit
history buffer — a snapshot of the status words at fault time (STRONG — `FUN_08001f74` /
`FUN_080026b6`). The vendor app reads them and shows them as raw hex in the report it asks
users to send to support, and this integration does the same: they are exposed verbatim as
diagnostic sensors and in the downloadable diagnostics.

Decoding them means matching the snapshot against the PRJSTAT bit maps above, for a fault
whose cause is known. See §7.

---

## 4. What the integration reads, and when

The integration is `local_push`. On connect it reads everything once and subscribes to the
characteristics that push:

| Subscribed (notify) | Read once per connection | Re-read on every 10 s cycle |
|---|---|---|
| current temperature, target temperature, PRJSTAT1, PRJSTAT2, PRJSTAT3, auto-off countdown, lifetime hours, lifetime minutes | serial number, all four version strings, auto-off setting, LED brightness, HIST1, HIST2 | current temperature, target temperature, PRJSTAT1 |

The 10 s cycle is a fallback, not the update mechanism. Notifications are unacknowledged
and the device only notifies on *change*, so a single dropped packet while the device holds
a temperature would otherwise freeze the reading indefinitely; re-reading the current
temperature repairs that.

Derived values, all computed in the integration rather than read from the device:

| Value | Derivation |
|---|---|
| Total heat time | `10110015 * 60 + 10110016` minutes |
| Current on time | auto-off setting (`1011000d`) − auto-off countdown (`1011000c`) |
| Ready | PRJSTAT1 bit 10 |
| HVAC action | heater off → `off`; heater on and bit 10 set → `idle`; heater on and bit 10 clear → `heating` |

---

## 5. Behaviour worth knowing before writing a client

**A write's confirmation can arrive before the write returns.** The device pushes the
PRJSTAT1 notification as soon as the heater or pump toggles, and that notification can be
delivered while the GATT write is still in flight. Any client that tracks "commands I sent
but have not seen confirmed" must record the pending write *before* sending it. Recording
it afterwards means the confirming notification is processed against no pending write,
the write is then recorded as still-pending, and a stale command gets replayed later — for
example turning the device back off moments after the user turned it on with the physical
button.

**Retrying commands is not symmetric.** Off-commands and temperature changes may be
replayed safely; on-commands must not be, because replaying a queued "on" against a device
the user has since switched off turns a vaporizer on unattended. This integration drops
every pending write whenever the device reports itself off.

**The device only reports whole degrees.** Values are transmitted ×10 but the tenths digit
is always zero, so rounding versus truncating makes no difference.

**Reading a characteristic is cheap; connecting is not.** Cold connects can take seconds,
especially through an ESPHome Bluetooth proxy, so nothing that runs at startup should block
on one.

---

## 6. Firmware update (bootloader) — documented, not implemented

The Volcano Hybrid can be re-flashed over BLE. This integration does not do it, on purpose.
The protocol is documented here anyway, because "it is impossible" would be wrong and the
real reasons are worth stating plainly.

### 6.1 The vendor's update flow

1. **Fetch the image.** `POST https://app.storz-bickel.com/firmwareHybrid` with body
   `version=false` returns the firmware as **hex text** plus `checksumOld` and
   `checksumNew`. With `version=true` the same endpoint returns only the published version,
   e.g. `[{"valid":1,"majorApplication":1,"minorApplication":3}]`.
   The image is served **unencrypted and unsigned** — the only integrity check is a CRC the
   bootloader recomputes, i.e. anti-corruption, not cryptographic. (The Venty/Veazy line
   differs: those images are AES-encrypted with a server-issued IV and key ID.)
2. **Enter the bootloader.** Write `uint16 4711` to `10100011` (the code-number
   characteristic — the one UUID this integration otherwise never touches), then request
   the boot status, which reboots the device into its bootloader.
3. **Talk the bootloader protocol** on service `00000002-1989-0108-1234-123456789abc`,
   a UART-style link with ASCII telegrams:

   ```
   FE FA 7F <len> <payload> 00 FD <xor-check>
   ```

   | Telegram | Purpose |
   |---|---|
   | `RV0` | Boot status; replies `RV0 222 BL…`, with the banner `222  Volcano  V01.03.00.0022` |
   | `Ra1` / `Ra2` | Page number / page size |
   | `We ` | Chip erase |
   | `Wp <page>` | Select page |
   | `Wd<idx> <hex>` | Write a 128-byte chunk |
   | `Wfp` | Flash the selected page |
   | `Rc ` | Read back CRC (compared against the server's `checksumNew`/`checksumOld`) |
   | `Wc <crc>` | Write CRC |
   | `Wl ` | Leave bootloader mode |

   Pages are 1024 bytes on the wire (2048-byte flash pages on the STM32F072), written with
   write-without-response and verified by CRC.

All of this is ordinary GATT. "Web Bluetooth", which the vendor app uses, is only the
browser's API for the same protocol; `bleak` could drive every step.

### 6.2 Why this integration does not flash firmware

- **An interrupted flash is the worst failure this integration could cause.** The vendor
  app holds one direct browser-to-device connection and tells the user to keep the device
  powered. Home Assistant may be going through an ESPHome Bluetooth proxy with its own
  reconnect and retry behaviour — a much less controlled link for a multi-minute write.
  Bootloader mode is at least detectable and resumable (the bootloader version string
  contains `BL`), so a failed flash is recoverable rather than terminal — but recovery
  still means going back to the vendor's browser app.
- **The firmware binary is Storz & Bickel's**, served from their endpoint. Downloading and
  pushing it from third-party software is a licensing question, not a technical one.

If it is ever built, it belongs behind an explicit opt-in, must refuse to start over a
proxied connection, and needs the CRC and page sequence verified against a device that can
be recovered.

### 6.3 How this integration reports firmware instead

The vaporizer cannot tell you whether newer firmware exists — only the vendor's server
knows. Calling that endpoint from every installation would put a cloud dependency behind an
otherwise fully offline `local_push` integration, so the newest verified firmware is
recorded in `custom_components/volcano_hybrid/firmware.py` and compared against what the
device reports. A scheduled workflow polls the vendor endpoint in CI and opens an issue
when it moves ahead, which is the signal to test and bump the constant by hand.

---

## 7. Unknowns, and how to settle them

What is still undecoded, in the order it is worth attacking:

1. **PRJSTAT1 error bits 3 and 14**, and the individual **PRJSTAT2 error bits**
   (`0x0001`, `0x0002`, `0x0008`, `0x0010`, `0x0020`).
2. **HIST1 / HIST2 layout** — the three 16-bit words are a snapshot of status registers,
   but which register lands in which word is not established.
3. **`10100003`**, the second firmware string.

The method for the error bits is observation, not more decompiling. Enable the *Status
register 1/2/3* and *Error history 1/2* diagnostic sensors, then when a real fault occurs —
the device shows an error, or the *Prv1 error* / *Prv2 error* sensors turn on — record:

- which bit inside the `ERR` mask is set (`0x4018` for PRJSTAT1, `0x003b` for PRJSTAT2),
- what the device was doing (heating, pumping, idle, just switched on),
- what physically happened (bag obstructed, pump blocked, overheat, filling chamber missing),
- the HIST1/HIST2 values, which hold the snapshot from the last fault.

Build the mapping from real cases and only then name the bits in code. A wrong label on a
fault sensor is worse than no label: it sends people to fix the wrong thing.

---

## 8. Sources

- **Vendor web app** (`js/volcano.js` from `app.storz-bickel.com`) — ground truth for
  service and characteristic UUIDs, the register write convention, and the bootloader
  telegram protocol.
- **Firmware decompile** — V01.03.00.0022, pulled unencrypted from the vendor's
  `firmwareHybrid` endpoint, decompiled with Ghidra and annotated with the STM32F072
  CMSIS-SVD. Source of the actuator-fault bit, the fault-snapshot behaviour, and the
  BLE-module-over-USART1 architecture. Target: STM32F072 (Cortex-M0), flash at
  `0x08000000`, 16 KB SRAM, 60 KB image, 122 functions.
- **Live observation** on a Volcano Hybrid running V01.03 — the three-state heat cycle in
  §3.1 and every bit tagged CONFIRMED (live).

Related documentation in this repository: [`README.md`](README.md) for the entities this
protocol is exposed as, [`CLAUDE.md`](CLAUDE.md) for the architecture of the integration
itself, and the downloadable diagnostics (**Settings → Devices & services → Volcano
Hybrid → Download diagnostics**) for a snapshot of all of the above from a running device.
