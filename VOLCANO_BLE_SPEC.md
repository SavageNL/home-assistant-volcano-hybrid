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
| **STRONG** | Derived from a decompile/disassembly of the V01.03 application firmware (STM32L4). Consistent, but not observed live. |
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

The GATT server is served by a **separate BLE module**; the STM32 main controller talks to
that module over **USART3**, with an ASCII telegram protocol whose full command set is in §10
(STRONG — image; an earlier read of the peripheral map put the module on USART1, which is
the wired service port and has its own dispatcher). The status registers below are the
controller's status words as forwarded to the module, which is why they read like internal
firmware state rather than a designed API.

The three PRJSTAT characteristics are the controller's own 16-bit status words at RAM
offsets `+0x14`, `+0x16` and `+0x18`, forwarded verbatim — the module does not remap or
renumber the bits. (STRONG — every bit whose meaning was established live is written at the
matching offset in the firmware.) The controller keeps **five** such words; `1010000f` and
`10100010` expose the other two. A V01.03 device serves both (CONFIRMED, live — §9), with
exactly the write properties the firmware's writable-bit whitelist predicts, but no bit in
either is decoded. This integration reads both as raw diagnostics (*Status register 4* /
*5*) without subscribing and without requiring them to exist.

The main controller is an **STM32L4 (Cortex-M4)**, specifically the L4x2/L4x3 line: the image
uses Thumb-2 instructions (`strd`, `tbb`, `cbz`, register-shifted loads), carries a
Cortex-M3/M4 vector table (MemManage / BusFault / UsageFault, SVC at `0x2C`, PendSV,
SysTick), and addresses its ADC at `0x50040000`, its GPIO bank at `0x48000000` and an
on-chip segment-LCD controller at `0x40002400`. Anyone re-deriving the firmware claims here
needs the matching SVD; register names taken from an STM32F0 SVD do not line up.

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
| `1011000c` | Auto-off countdown — the **session** countdown (§2) | `uint16`, seconds remaining | Read + **notify**. Runs from the moment an actuator is switched on; `0` when not running. CONFIRMED (live) |
| `1011000d` | Auto-off setting — seeds `1011000c` | `uint16`, seconds | Read/write. The UI offers 0–360 min in 30-min steps. CONFIRMED (live) |
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

**Auto-off is three countdowns.** The controller decrements each of them once per second
(STRONG — the 1 Hz handler, and every writer of the three words swept across the image):

| Counter | Loaded when | Loaded from | On reaching zero |
|---|---|---|---|
| Heater timeout | the heater is switched on | a config word, factory default 65535 s; not exposed in this service | heater off |
| Session timeout | the heater **or** the pump is switched on | a config word, factory default 1800 s, exposed as `1011000d` | heater **and** pump off |
| Second-stage timeout | the second stage is switched on (PRJSTAT1 bit 6) | fixed 180 s | second stage off |

**The heater timeout starts when the target is first reached, not when the heater is switched
on.** Until PRJSTAT1 bit 9 sets, the control loop reloads that counter to its full value on
every pass, so a long heat-up does not count against it. The session timeout has no such gate
and runs from the moment its actuator starts.

Nothing else reloads them: key presses, setpoint changes and temperature notifications leave
all three alone. The only other writers are the interlocks, which zero all three while the
heater is off — which is why the countdown reads `0` on an idle device — and **PRJSTAT2
bit 7**, which reloads the first two every second and so suspends auto-off entirely while it
is set.

The controller exports each countdown and each setting as its own telegram register and does no
combining. **`1011000c` is the session countdown and `1011000d` its setting** (CONFIRMED, live):
switching the heater on from cold at 30 °C with a 178 °C target, the countdown started at the
configured 60.0 minutes and fell one second per second while the block heated — behaviour only
the session counter has, since the heater counter is pinned at full value until the target is
first reached. The heater countdown and the second-stage countdown are not exposed in this
service.

A `setting − countdown` derivation is therefore valid for this pair.

---

## 3. Service `10100000` — status, identity and history

| Characteristic | Used as | Encoding | Notes |
|---|---|---|---|
| `10100001` | Bootloader version | ASCII string | Contains `BL` while the device sits in bootloader mode — that is how a half-finished flash is detectable. CONFIRMED |
| `10100003` | Firmware string | ASCII string | A second version/identity string. This integration only uses it as a fallback when `10100005` is empty. Exact meaning unconfirmed. SPECULATIVE |
| `10100004` | BLE-module firmware version | ASCII string | The version of the BLE module, not the main controller. CONFIRMED |
| `10100005` | Firmware version | ASCII string, e.g. `V01.03` | The application firmware of the main controller. This is the version that tracks Storz & Bickel's published releases. CONFIRMED |
| `10100006` | Mains voltage | ASCII string | Read back as `230VAC` on a European V01.03 device: the mains the unit was built for. Advertises write (§9); **nothing writes it** — it describes the hardware, not a setting. CONFIRMED (live) |
| `10100007` | Model | ASCII string | Read back as `HYBRID`: the device's own name for its model class — the same Hybrid/Medic distinction PRJSTAT3 bit 0 is seeded from at boot (§3.3), though nothing ties the two together beyond the name. Advertises write (§9); **nothing writes it**. CONFIRMED (live) |
| `10100008` | Serial number | ASCII string, space-padded | CONFIRMED |
| `1010000c` | **PRJSTAT1** | `uint16` bit field | Read + **notify** + write. Live device state: heater, pump, ready, faults. Writable at the GATT layer, but the §3.4 convention does not take on it and writing it can switch the pump off — **do not write it** (§3.7). §3.1 |
| `1010000d` | **PRJSTAT2** | `uint16` bit field | Read + **notify** + write (see §3.4). Display settings and a second error group. §3.2 |
| `1010000e` | **PRJSTAT3** | `uint16` bit field | Read + **notify** + write (see §3.4). Vibration setting. §3.3 |
| `1010000f` | **PRJSTAT4** | `uint16` bit field | The controller's fourth status word (§1). Served as read/write + notify (CONFIRMED, live — §9); identification as PRJSTAT4 STRONG. No bit decoded; read once, not subscribed, and its absence is tolerated |
| `10100010` | **PRJSTAT5** | `uint16` bit field | The fifth status word, on the same terms — but served read + **notify** only, matching the one register for which the firmware's whitelist has no writable bits (§9). Identification STRONG, contents undecoded |
| `10100011` | Code number | `uint16` write | Writing `4711` unlocks entry into the bootloader. Not touched by this integration. CONFIRMED (vendor app) |
| `10100015` | **HIST1** | ASCII hex text | Fault log — recent fault codes and/or per-code counts. Encoding CONFIRMED (live); contents undecoded. §3.5 |
| `10100016` | **HIST2** | ASCII hex text | The other half of the fault log, same encoding. §3.5 |

### 3.1 PRJSTAT1 — `1010000c`

The one register that matters for live state. It is a notify characteristic, so every
change is pushed.

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 0 | `0x0001` | Heater **requested** — the switch, not the element (see below) | CONFIRMED (live) |
| 1 | `0x0002` | Heater **interlock passed** — set only while bits 0 and 5 are both set and no heater fault is latched | STRONG |
| 3 | `0x0008` | **Heater fault, logged as code `0x3C`** — inhibits the heater only | STRONG |
| 4 | `0x0010` | **Fault, logged as code `0x3D`** — inhibits **both** the heater and the pump | STRONG |
| 5 | `0x0020` | Heat regulation running (`HEIZUNG_ENA`) | CONFIRMED |
| 6 | `0x0040` | Second temperature stage ("boost") — adds a configurable offset to the target. Host-settable; no front-panel key reaches it | STRONG |
| 7 | `0x0080` | Control-loop mode: clear = PID control (normal), set = on/off control | STRONG |
| 8 | `0x0100` | Selects how the regulation value is scaled in the validation path: raw, or divided by 10 and linearly transformed. Internal, host-settable | STRONG |
| 9 | `0x0200` | Target has been reached at least once this heating cycle — set every pass while `target − current ≤ 0`, cleared only when the heater goes off. Also gates the start of the heater auto-off countdown (§2) | CONFIRMED (live) |
| 10 | `0x0400` | **Setpoint reached** — set the moment `current ≥ target`; cleared only by *raising* the target ≥3.0 °C (§3.1.1) | CONFIRMED (live) |
| 12 | `0x1000` | Pump/fan **requested** | STRONG |
| 13 | `0x2000` | Pump/fan FET enabled (`PUMPE_FET_ENABLE`) — set while bit 12 is set and no pump fault is latched | CONFIRMED |
| 14 | `0x4000` | **Pump interlock fault** — read as a pump inhibit, but *never written* by the application firmware (see below) | STRONG |
| 15 | `0x8000` | Air step mode — makes the physical AIR button cycle the pump 100 % → 75 % → 50 % → off instead of toggling. Host-settable, but no way to set it has been found: a §3.4 mask write does not latch it (§3.7) | STRONG |
| — | `0x4018` | `ERR` — the OR of bits 3, 4 and 14 | CONFIRMED |

The `0x4018` bits are the actuator interlocks. Two functions run every control pass and decide
whether each actuator may run (STRONG):

| Interlock | Inhibits on | Clears on a fault |
|---|---|---|
| Heater | bit 3, bit 4, or any of the five PRJSTAT2 error bits (§3.2) | bits 0 and 1 |
| Pump | bit 14, bit 4, or the same five PRJSTAT2 bits | bits 12 and 13 |

Bit 3 stops the heater, bit 14 stops the pump, bit 4 stops both. Because the heater interlock
clears bits 0 and 1, a faulted device reports itself switched off.

Bits 3 and 4 come from the same check in the heater control state machine: at two points it
measures an elapsed tick count, and raises the bit when the count is under 100, logging code
`0x3C` and `0x3D` respectively. The bit clears once the count reaches 100. What the counters
measure is not established — surface these as timing faults, not as a named cause.

Bit 14 is read by the pump interlock but written nowhere in the application image, so it should
always read 0 on this firmware. It may be set from the bootloader-resident region (§6), or be
vestigial. Do not build a fault indicator on it without observing it set on a device.

The three-state observation that established bit 10, taken on one device across a full heat
cycle with a 40 °C setpoint:

| | Off / cold | Heating, 31 °C (below target) | At target, 40 °C |
|---|:--:|:--:|:--:|
| PRJSTAT1 | `0x0000` | `0x0023` | `0x0623` |
| bit 10 `0x0400` (reached) | 0 | 0 | **1** |
| bit 9 `0x0200` (auto shutdown) | 0 | 0 | **1** |
| bits 0, 1, 5 (heater) | 0 | 1 | 1 |

`0x0623 ^ 0x0023 = 0x0600`: bits 9 and 10 both flip on first reaching temperature. Bit 9 is
not a "heating" signal, and — unlike bit 10 — it does not flip back afterwards: raising the
setpoint again clears bit 10 while bit 9 stays set (`0x0223`). Only switching the heater off
clears it.

#### 3.1.1 When bit 10 sets and clears

```
set:    current >= target                     →  bit 10 = 1
clear:  new_target >= previous_target + 3.0   →  bit 10 = 0
```

Both sites use the same constant, `0x1e` = 30 tenths = 3.0 °C (STRONG — the set site in the
heater control loop, the clear sites in the BLE-write and front-panel paths).

The bit is a latch: it means the device got to temperature, not that it is at temperature now.
The set side has no tolerance. The clear side compares the new target against the **previous
target**, never against the current reading, so raising the target by 3.0 °C or more clears the
bit and lowering it never does.

Bit 9 is set by the same `current >= target` test on the same pass. It has no clear path, which
is why it stays set once the device has reached temperature.

Measured on one device, raising the setpoint in steps while it held temperature (CONFIRMED,
live):

| Setpoint change | Bit 10 cleared? | PRJSTAT1 |
|---|:--:|---|
| 180 → 181 (+1) | no | `0x0623` unchanged |
| 181 → 183 (+2) | no | `0x0623` unchanged |
| 183 → 186 (+3) | **yes**, for 10.7 s | `0x0623` → `0x0223` → `0x0623` |
| 186 → 190 (+4) | **yes**, for 10.7 s | `0x0623` → `0x0223` → `0x0623` |
| 190 → 170 (−20) | no | `0x0623` unchanged for the whole coast down |

The 10.7 s is the time the element took to close the new gap and re-satisfy `current >= target`.
There is no timer on the bit.

On settling, bit 10 was once seen to clear and re-set within a single second, which shows up as
a one-frame flicker in anything driven straight off it.

**Switching the heater off clears the whole register at once.** PRJSTAT1 goes to `0x0000`
the instant the heater is switched off — indistinguishable from a stone-cold device, even
with the block still at 170 °C and the display lit. **The cooldown phase is not observable**
(CONFIRMED, live); see §4 for how the integration infers it.

The controller does this in one step: the moment bit 0 reads clear it masks PRJSTAT1 with
`& ~0x0660`, wiping bits 5, 6, 9 and 10 together, while the interlock functions drop bits 1,
12 and 13. No cooldown state is retained anywhere in the register (STRONG).

#### 3.1.2 No bit reports the element being energised

**Bits 0, 1 and 5 track the heater switch, not the element.** Bit 5 means the regulation loop
is running; bit 1 is bit 0 AND bit 5, gated by the interlock. In the normal control mode all
three follow the switch. Holding at a 180 °C setpoint for 3 minutes 40 seconds, PRJSTAT1 stayed
at `0x0623` without a single change while the element was necessarily cycling to hold
temperature (CONFIRMED, live). To show whether the device is working towards its setpoint, a
client must compare the reported current temperature against the target (§4).

This follows from the control loop. With bit 7 clear — the normal mode — the controller runs a
**PID loop** whose output is a percentage, not a decision. Every 100 ms it computes `P + I + D`
from the error in tenths of a degree, using gains 300, 20 and 500 from the config block, clamps
the sum to 0…100000, scales it to 0–100 %, and maps that through a 101-entry lookup table to a
mains phase angle. The element runs at a continuously varying fraction of full power; P alone
saturates at an error of 33.3 °C, so a larger gap means full power and the taper happens inside
that band. The percentage is never exported and no bit encodes it.

With **bit 7 set** the controller uses on/off control instead, and bit 5 becomes the demand
signal: set when the target is more than 1.0 °C above the reading, cleared when the reading
passes 1.0 °C above the target, driving the element at 100 % while set. Bit 5 is an element
signal only in this mode.

Nothing in the firmware sets bit 7; it is host-settable only, and whether any characteristic
reaches the underlying command is decided in the BLE module. On/off control widens temperature
swings and increases thermal cycling on a mains-heated aluminium block, so treat it as a
diagnostic path rather than a feature (STRONG).

### 3.2 PRJSTAT2 — `1010000d`

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 0 | `0x0001` | **Regulation sample out of range** — logs code `0x3F` when the averaged sample exceeds 799, or `0x2D` when it is pinned below 4 | STRONG |
| 1 | `0x0002` | **Regulation value outside its valid window** — logs code `0x40` | STRONG |
| 3 | `0x0008` | **Heartbeat / comms timeout** — an internal counter reached 5000 ticks without being serviced; logs code `0x41` | STRONG |
| 4 | `0x0010` | **Heater power/resistance feedback low** (below 6250) — logs code `0x43` | STRONG |
| 5 | `0x0020` | **Heater power/resistance feedback high** (above 34500) — logs code `0x44` | STRONG |
| 6 | `0x0040` | Service / burn-in mode active (entered from the front panel, see §3.6) | STRONG |
| 7 | `0x0080` | **Auto-off hold** — while set, both auto-off countdowns are reloaded every second and never expire. Host-settable | STRONG |
| 8 | `0x0100` | Host-settable flag, purpose undecoded | STRONG |
| 9 | `0x0200` | Display in Fahrenheit (**0 means Celsius**) | CONFIRMED |
| 10 | `0x0400` | Keypad test armed (production test, see §3.6) | STRONG |
| 11 | `0x0800` | Settings-changed notification flag | STRONG |
| 12 | `0x1000` | Display stays on while cooling (**0 means enabled**) | CONFIRMED |
| 13 | `0x2000` | Displayed temperature has settled — clear while the shown value is still stepping toward the reading | CONFIRMED (mechanism) |
| — | `0x003b` | `ERR` — the OR of bits 0, 1, 3, 4 and 5 | CONFIRMED |

Note the inverted polarity of bits 9 and 12: the clear bit is the enabled state.

All five `0x003b` bits inhibit **both** actuators: each interlock tests the whole group, so any
one of them switches the device off and makes PRJSTAT1 read as not running (STRONG). The group
is a latched summary of the heater-regulation loop's own faults, which is why it duplicates no
PRJSTAT1 bit — PRJSTAT1 carries the switch state and the timing faults, PRJSTAT2 the regulation
and feedback faults.

Bits 4 and 5 bracket the heater's measured power/resistance feedback: low reads as an open or
under-driven element, high as an over-current or shorted one. Bit 3 is a watchdog on internal
servicing, not a thermocouple, overtemperature or bag-detection event; do not label it as a
sensor fault. Genuine sensor faults appear in the history as codes `0x35` (reading pinned below
40.0 °C, short) and `0x36` (reading pinned near `0xFFFF`, open).

Bit 13 belongs to the display, not the thermal system. The display module walks its shown value
toward the real reading in 1.0 °C steps, clearing bit 13 during the walk and setting it once the
values match, so the bit dips once per displayed degree of change and is steady otherwise. Live,
this reads as a pulse whose rate tracks how fast the temperature is moving: throughout a
cooldown every dip fell within ±0.6 s of a 1 °C step. It is not a cooldown signal and not a
measurement strobe. Clients watching PRJSTAT2 for settings changes should mask it out.

### 3.2.1 Fault codes

The bits above say *that* something failed; the history characteristics (§3.5) say *what*.
The complete code table recovered from the firmware:

| Code | Meaning |
|---:|---|
| `0x2D` (45) | Regulation reading pinned **low** (below 4) |
| `0x35` (53) | **Temperature sensor short** — reading below 400 (40.0 °C) |
| `0x36` (54) | **Temperature sensor open** — reading pinned near `0xFFFF` |
| `0x3C` (60) | Heater regulation timing fault — raises PRJSTAT1 bit 3 |
| `0x3D` (61) | Heater regulation timing fault — raises PRJSTAT1 bit 4 |
| `0x3F` (63) | Regulation average **too high** (above 799) |
| `0x40` (64) | Regulation value **outside its valid window** |
| `0x41` (65) | **Heartbeat / comms timeout** (5000 ticks) |
| `0x43` (67) | Heater feedback **low** (below 6250) |
| `0x44` (68) | Heater feedback **high** (above 34500) |
| `0x48` (72) | Heater feedback **deviation** beyond its band |

### 3.3 PRJSTAT3 — `1010000e`

| Bit | Mask | Meaning | Confidence |
|---:|---:|---|---|
| 0 | `0x0001` | Hardware-option flag — seeded at boot from the model class, and **toggleable from the front panel** (§3.6). Gates an accessory sense/drive line on the board | STRONG |
| 5 | `0x0020` | Enables entry into the service / burn-in mode (§3.6) | STRONG |
| 6 | `0x0040` | Saved copy of bit 0, written during shutdown | STRONG |
| 10 | `0x0400` | Vibration (**0 means enabled**) | CONFIRMED |
| 12 | `0x1000` | Mirror of PRJSTAT1 bit 10 — set at the setpoint (`0x0467` → `0x1467`) | CONFIRMED (live) |

The firmware sets and clears bit 12 at the same sites as PRJSTAT1 bit 10, and it tracked that
bit exactly across a full cycle, including the drop to `0x0467` when the heater goes off. Use
PRJSTAT1 bit 10 for "ready" — PRJSTAT1 is the register the device pushes on change.

Bit 0 is set for Hybrid-class units and clear for Medic-class ones at boot. When set, the
controller drives one GPIO low, samples a second as an input (reflecting it into bit 2) and
drives a third from bit 4; when clear it tears that down and configures two interrupt inputs
instead. Which accessory or sensor that line serves is not established, so treat the bit as
read-only.

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

**PRJSTAT1 does not accept this convention**, and that is a measured result rather than a
property of the characteristic: `1010000c` advertises write like the other two (§9), and the
firmware's telegram handler does list PRJSTAT1 bits 7, 8 and 15 as host-settable. A set-mask
write to it nevertheless fails to latch, and has a side effect — see §3.7. Use the heater and
pump command characteristics (§2) and leave PRJSTAT1 alone.

### 3.5 HIST1 / HIST2 — `10100015` / `10100016`

The device's fault log, as **ASCII text** — the characters, not the bytes they spell. CONFIRMED
(live): a V01.03 device answered both with 16 bytes that are 16 printable characters.

| Characteristic | Bytes on the wire | Decoded as text |
|---|---|---|
| `10100015` | `36313631363136313631363137323631` | `6161616161617261` |
| `10100016` | `30303030303030303030303030303030` | `0000000000000000` |

A client that hexes the raw bytes therefore reports the value encoded twice; take the text.

**Read the text as eight two-character decimal fields**, each one a fault code from §3.2.1 —
which lists every code as hex with its decimal in brackets, and the log spells the decimal. `00`
is an empty slot, not a code. The two readings above decode as:

| Text | Fields | Meaning |
|---|---|---|
| `6161616161617261` | `61 61 61 61 61 61 72 61` | seven × `0x3D` heater regulation timing fault (the one that raises PRJSTAT1 bit 4), one × `0x48` heater feedback deviation |
| `0000000000000000` | `00 00 00 00 00 00 00 00` | eight empty slots — nothing logged |

The **encoding and the field rule** are CONFIRMED (live), and the argument is that two different
readings both land on documented values under this rule while neither does under the byte
reading. Under the field rule, `61` and `72` are `0x3D` and `0x48`, both in §3.2.1, and `00` is
the empty slot; read instead as hex bytes, the same characters are `0x61` and `0x72`, which
appear in no table at all, and the second value would be eight `0x30` bytes, which is not a code
either. One value fitting could be a coincidence; two distinct ones fitting, where the
alternative fits neither, is not.

What the two characteristics *are* is a separate question and is still open — see below and §7.
The firmware maintains the log in two parts (STRONG — the two logging routines and all of their
callers):

- a **16-entry ring buffer of code bytes**, most recent first; every fault pushes its code;
- a **per-code counter array**, saturating at `0xfff0`, holding how many times each code has
  occurred.

Neither structure holds a timestamp or a captured temperature, so the log gives what failed and
how often, never when or at what temperature.

Two cautions about reading more into this than the wire supports:

- **The log as served is eight entries deep**, not the sixteen the ring buffer was read as
  holding. Sixteen characters are eight fields, and the count of *entries* is what a client can
  see; whether the buffer behind the characteristic is longer and this is a window onto it is not
  visible from the wire. Take 8 as the depth on this firmware.
- **Most-recent-first is the firmware reading, not an observation.** The order of the fields as
  served has not been checked against a device where the sequence of faults was known, so a
  client presenting "most recent" is repeating this document's claim, not a measurement.

The vendor app reads both and shows them as raw hex in the report it asks users to send to
support. This integration exposes both verbatim as diagnostic sensors and in the downloadable
diagnostics, and decodes them into a *Last fault* sensor that reports the first entry of
`10100015` with the whole decode in its attributes — raw text included, empty slots and all.

### 3.6 The front panel can change these registers too

The front-panel keys write several of the same bits, so these registers can change with no BLE
write outstanding (STRONG — the controller's key handler). Only the register effects are listed
here; the full front-panel behaviour is out of scope for a BLE spec.

| Keys | Effect on the registers |
|---|---|
| **HEAT** | toggles PRJSTAT1 bit 0 |
| **AIR** | toggles PRJSTAT1 bit 12 — unless PRJSTAT1 bit 15 is set, in which case it steps the pump 100/75/50/off |
| **+** / **−** | change the target by 1.0 °C per step, and clear PRJSTAT1 bit 10 under the §3.1.1 rule. **Both keys are inert while the heater is off** — the front panel cannot set a temperature on a cold device, only a BLE client can |
| **−** and **+** together, ~0.5 s | **toggles PRJSTAT2 bit 9 (°C ↔ °F)** — also only while the heater is on |
| **−** and **AIR** together, ~0.5 s | toggles PRJSTAT3 bit 0, on Hybrid-class units only |
| **HEAT** and **AIR** together, ~3 s | enters the service / burn-in mode: sets PRJSTAT2 bit 6, forces the target to 230.0 °C, forces Celsius, switches the heater on and the pump off, and sets the heat auto-off to 600 s. Requires PRJSTAT3 bit 5 and both actuators already off |

Two consequences for a client. The °C/°F setting and the target can change unprompted, so a
last write is not authoritative. And PRJSTAT2 bit 6 reading set means the device is in a mode
that drives itself to maximum temperature for ten minutes — surface it rather than ignoring it.

PRJSTAT2 bit 10 arms a production keypad test, which requires all five keys to be pressed once
each. The panel has a fifth key that does nothing in normal operation.

### 3.7 Writing PRJSTAT1 — a recorded negative result

This is written up so nobody repeats it. The attempt was to turn on air step mode (PRJSTAT1
bit 15, §3.1) from a client by writing the §3.4 set-mask word — 4-byte little-endian
`0x00008000` — to `1010000c`. Every write was accepted at the ATT layer: `write_gatt_char`
returned without raising in all three runs. Nothing about the outcome was visible from the
write alone.

Three runs on one V01.03 device (CONFIRMED, live):

| Run | State before | PRJSTAT1 before | Read-back delay | PRJSTAT1 read back | Durable outcome |
|---|---|---|---|---|---|
| 1 | pump on, heater off | `0x3000` | ~0.61 s | `0x0000` | pump **stopped**, confirmed by the device (fan state went off with no pending write) |
| 2 | pump on 88 s, heater off | `0x3000` | ~0.61 s | `0x0000` | pump **stopped** again |
| 3 | heater on, pump off | `0x0623` | ~0.19 s | `0x8000` | register reverted to `0x0623` within ~0.3 s; **heater kept running**; bit 15 not retained |

What the runs establish:

- **The write reaches the controller and has a real effect.** The pump stopped within a second
  of the write, twice, with the device itself reporting the off state. It had been running 48 s
  and 88 s respectively, so no fixed timeout explains it. CONFIRMED (live).
- **Bit 15 does not latch.** Run 3 read the register back as the written word and then watched
  it revert to its true value with the heater still on. CONFIRMED (live).
- The explanation that fits all three runs is that the write briefly forces PRJSTAT1 to the
  written word, and the control loop then re-derives the register from its own internal state on
  the next pass. That re-asserts the heater's bits (run 3) but not the pump's, because the pump
  FET follows bit 13 directly, so the forced clear of bits 12 and 13 is taken as a genuine
  pump-off (runs 1 and 2). SPECULATIVE — it fits the data and has not been checked against the
  firmware.

For a client the conclusion is flat: **the §3.4 set/clear convention does not work on PRJSTAT1,
and writing to PRJSTAT1 can switch the pump off.** Do not write it. CONFIRMED.

The three bits the firmware's whitelist marks host-settable on PRJSTAT1 are 7, 8 and 15 (§9);
only bit 15 was tried. Whatever path does reach them, it is not this one.

---

## 4. What the integration reads, and when

The integration is `local_push`. On connect it reads everything once and subscribes to the
characteristics that push:

| Subscribed (notify) | Read once per connection | Re-read on every 10 s cycle |
|---|---|---|
| current temperature, target temperature, PRJSTAT1, PRJSTAT2, PRJSTAT3, auto-off countdown, lifetime hours, lifetime minutes | serial number, model, mains voltage, all four version strings, auto-off setting, LED brightness, HIST1, HIST2, PRJSTAT4, PRJSTAT5 | current temperature, target temperature, PRJSTAT1 |

The 10 s cycle is a fallback, not the update mechanism. Notifications are unacknowledged
and the device only notifies on *change*, so a single dropped packet while the device holds
a temperature would otherwise freeze the reading indefinitely; re-reading the current
temperature repairs that.

Derived values, all computed in the integration rather than read from the device:

| Value | Derivation |
|---|---|
| Total heat time | `10110015 * 60 + 10110016` minutes |
| Current on time | auto-off setting (`1011000d`) − auto-off countdown (`1011000c`); a matched pair, both the session timer (§2) |
| Ready | PRJSTAT1 bit 10, verbatim — so it only re-arms when the target is raised ≥3 °C, and stays on while the device coasts down (§3.1.1) |
| Heating | current temperature < target temperature. Not bit 10, which does not track the gap, and no element signal exists to use instead (§3.1.2) |
| Cooling | heater off, display-on-while-cooling enabled (PRJSTAT2 bit 12) and current temperature ≥ 40 °C. Inferred — the device reports nothing during cooldown |
| HVAC action | heater on and heating → `heating`; heater on and holding → *none reported*, so the card names the mode; heater off and cooling → `idle`; otherwise → `off` |

---

## 5. Client implementation notes

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

The Volcano Hybrid can be re-flashed over BLE. The protocol is documented here; §6.2 gives the
reasons this integration does not implement it.

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

   Pages are 1024 bytes on the wire (2048-byte flash pages on the controller), written with
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

1. **What PRJSTAT1 bits 3 and 4 physically measure.** The mechanism is known — an elapsed tick
   count coming in under 100 at two points in the heater state machine — but not what is being
   timed, so the codes `0x3C` / `0x3D` should be surfaced as codes, not as named causes.
2. **PRJSTAT1 bit 14.** Read as a pump inhibit, written by nothing in the application image.
   Either it comes from the bootloader-resident region or it is dead. Worth watching, not
   worth labelling.
3. **What HIST1 and HIST2 actually hold.** Both the encoding and the field rule are settled
   (ASCII text, eight two-digit decimal fields, each a §3.2.1 code — §3.5), so the codes in a log
   can now be read. Two things about the log are not settled. **Which characteristic is the ring
   and which the per-code counters**: the one device read so far had codes in `10100015` and
   nothing but empty slots in `10100016`, which is what an unused counter array and an unused
   ring look like alike — and a counter saturating at `0xfff0` does not fit a two-digit decimal
   field, so if `10100016` is the counters they are not served verbatim. And **whether the order
   really is most recent first**, which is how the firmware maintains the ring but has never been
   checked against a device where the sequence of faults was known. Both are settled by one
   reading: a device with a real fault history, logged as it happens.
4. **The undecoded host-settable flags**: PRJSTAT2 bit 8, and the purpose of the hardware line
   PRJSTAT3 bit 0 gates.
5. **`10100003`**, which is a second copy of the application version string rather than a
   distinct identity — but which telegram backs it is decided in the BLE module, not the
   controller.
6. **PRJSTAT4 and PRJSTAT5** (`1010000f` / `10100010`) — what the controller's other two status
   words carry. That the module serves them is now settled (§9), so the *Status register 4/5*
   diagnostic sensors do report a value; watching them across a heat cycle is the next step.
7. **How to latch PRJSTAT1 bit 15**, and the other two bits its whitelist marks host-settable.
   The controller plainly supports the telegram, but the §3.4 mask write does not take (§3.7).
   Whatever the vendor app does to reach these bits, it is something else.
8. **What service `10130000` is.** Eleven read-only characteristics plus one read/write/notify
   at `101300ff`, none of them decoded and none mentioned by the vendor app (§9). Reading them
   on a device and watching whether any move is where this starts.
9. **Which characteristic, if any, is bound to the `G Q` pump-percent telegram.** The telegram
   itself is settled: `G Q <pct>` writes config `+0x40`, ungated, 0–100 (§10.5). What is not
   settled is whether the BLE module binds any characteristic to it. That binding lives in the
   **radio module's firmware, which is not in the controller image** (§10.6), so this question is
   not answerable by more work on the controller dump — it needs the module's firmware, or a
   device to test against. `10110004` is the best positional candidate and its read value argues
   against it (§10.6); a wrong guess here writes to the pump (§9.2).

Items 1, 3, 4 and 6–9 are settled by observation rather than more decompiling. Enable the *Status
register 1/2/3*, *Error history 1/2* and *Last fault* diagnostic sensors, then when a real fault
occurs — the device shows an error, or the *Prv1 error* / *Prv2 error* sensors turn on — record:

- which bit inside the `ERR` mask is set (`0x4018` for PRJSTAT1, `0x003b` for PRJSTAT2),
- what the device was doing (heating, pumping, idle, just switched on),
- what physically happened (bag obstructed, pump blocked, overheat, filling chamber missing),
- the HIST1/HIST2 values, and which end of them moved.

The names in §3.2 are the conditions the firmware itself tests, which is as far as static
analysis reaches; confirming each against a reproduced fault is the remaining step. A wrong
label on a fault sensor is worse than no label, because it sends people to fix the wrong thing.

---

## 8. Sources

- **Vendor web app** (`js/volcano.js` from `app.storz-bickel.com`) — ground truth for
  service and characteristic UUIDs, the register write convention, and the bootloader
  telegram protocol.
- **Firmware decompile** — V01.03.00.0022, pulled unencrypted from the vendor's
  `firmwareHybrid` endpoint, decompiled with Ghidra and cross-checked by direct Thumb-2
  disassembly to resolve the literal-pool pointers the decompiler leaves anonymous. That
  resolution is what makes the status words readable: with `0x20001E58` identified as the
  status block, every `orr`/`bic` against `+0x14`/`+0x16`/`+0x18` can be enumerated and
  attributed. Source of the bit maps (§3.1–§3.3), the interlock semantics, the
  reached-bit rule (§3.1.1), the fault-code table (§3.2.1), the history layout (§3.5) and the
  front-panel effects (§3.6). Target: **STM32L4 (Cortex-M4)**, application flashed at
  `0x08000000`, 60 KB image, 293 functions recovered.
  The image references code and data at `0x08014000`+ that it does not contain — the
  bootloader region — so a few things (including whatever sets PRJSTAT1 bit 14) are not
  answerable from it.
- **Full disassembly of the same image** (`volcano_hybrid_1.3.bin`, Capstone, Thumb-2/M4) —
  source of the USART telegram command set, both dispatch tables and the passcode-gated
  commands in §10. It also marks the boundary of what this image can answer: the module's
  characteristic→telegram bindings live in the radio module's firmware, which is not part of
  it, so no further work on the controller image settles them (§10.6).
- **Live observation** on a Volcano Hybrid running V01.03 — the three-state heat cycle in
  §3.1, the tolerance-band and cooldown measurements in §3.1.1, and every bit tagged
  CONFIRMED (live).

Related documentation in this repository: [`README.md`](README.md) for the entities this
protocol is exposed as, [`CLAUDE.md`](CLAUDE.md) for the architecture of the integration
itself, and the downloadable diagnostics (**Settings → Devices & services → Volcano
Hybrid → Download diagnostics**) for a snapshot of all of the above from a running device.

---

## 9. Appendix — the GATT table as observed

Enumerated with `bleak` (`char.properties`) from **one** Volcano Hybrid running V01.03; the
handles are from that enumeration. The GATT server belongs to the BLE module, not the
controller (§1), so another module revision may serve a different set or different properties —
read this as one device's table, not as a specification. CONFIRMED (live) for that device.

Characteristics documented elsewhere in this file are named here for orientation only.
Everything else is listed as **undecoded**: it was served, and nothing more than that is
claimed. Note in particular that *write* below means only that the characteristic advertises
the property; §3.7 is what happens when an advertised write is taken at face value, and §10.7
is what sits behind the ones whose binding nobody has established.

### 9.1 Service `10100000` — status, identity and history

| Characteristic | Handle | Properties | Documented as |
|---|---:|---|---|
| `10100001` | 21 | read | Bootloader version (§3) |
| `10100002` | 23 | read | undecoded |
| `10100003` | 25 | read | Firmware string (§3) |
| `10100004` | 27 | read | BLE-module firmware version (§3) |
| `10100005` | 29 | read | Firmware version (§3) |
| `10100006` | 31 | read, write | Mains voltage — `230VAC` (§3) |
| `10100007` | 33 | read, write | Model — `HYBRID` (§3) |
| `10100008` | 35 | read, write | Serial number (§3) |
| `10100009` | 37 | read, write | undecoded |
| `1010000a` | 39 | read, write | undecoded |
| `1010000b` | 41 | read | undecoded |
| `1010000c` | 43 | read, write, notify | **PRJSTAT1** (§3.1) — writable, but see §3.7 |
| `1010000d` | 46 | read, write, notify | **PRJSTAT2** (§3.2) |
| `1010000e` | 49 | read, write, notify | **PRJSTAT3** (§3.3) |
| `1010000f` | 52 | read, write, notify | **PRJSTAT4** (§1) |
| `10100010` | 55 | read, notify | **PRJSTAT5** (§1) |
| `10100011` | 58 | read, write | Code number — `4711` unlocks the bootloader (§6) |
| `10100012` | 60 | read, write | undecoded |
| `10100013` | 62 | read, write | undecoded |
| `10100014` | 64 | read, write | undecoded |
| `10100015` | 66 | read | **HIST1** (§3.5) |
| `10100016` | 68 | read | **HIST2** (§3.5) |

### 9.2 Service `10110000` — control and settings

| Characteristic | Handle | Properties | Documented as |
|---|---:|---|---|
| `10110001` | 71 | read, notify | Current temperature (§2) |
| `10110002` | 74 | read | undecoded |
| `10110003` | 76 | read, write, notify | Target temperature (§2) |
| `10110004` | 79 | read, write, notify | undecoded — pump-power candidate, see below |
| `10110005` | 82 | read, write | LED brightness (§2) |
| `1011000c` | 84 | read, notify | Auto-off countdown, session timer (§2) |
| `1011000d` | 87 | read, write | Auto-off setting (§2) |
| `1011000e` | 89 | read, notify | undecoded |
| `1011000f` | 92 | read, write | Heater **on** (§2) |
| `10110010` | 94 | read, write | Heater **off** (§2) |
| `10110011` | 96 | read, write | undecoded |
| `10110012` | 98 | read, write | undecoded |
| `10110013` | 100 | read, write | Pump **on** (§2) |
| `10110014` | 102 | read, write | Pump **off** (§2) |
| `10110015` | 104 | read, notify | Lifetime heater hours (§2) |
| `10110016` | 107 | read, notify | Lifetime heater minutes (§2) |
| `10110017` | 110 | read, notify | undecoded |

`10110006`–`1011000b` are not served at all: the numbering jumps straight from `10110005` to
`1011000c`.

**`10110004` is a candidate for the pump-power command** (SPECULATIVE). The firmware has a
`G Q <pct>` telegram that sets pump power to 0–100 % with no gating of any kind, and this is an
undecoded read/write/notify characteristic sitting immediately after the target temperature —
and a `uint16` percentage is already how LED brightness is carried two characteristics along.
Nothing has tested it. It is a guess from position and shape only, and the cost of a wrong guess
is a write to something that drives the pump.

Two later findings argue against it without settling it (§10.6): the module's characteristic map
is not an order-preserving projection of the controller's command set, so position carries less
than it looks like it does; and `10110004` read `0` both idle and with the pump at full speed,
where anything mirroring `cfg+0x40` should read its factory default of 100. The candidacy stays
SPECULATIVE and is not to be acted on.

### 9.3 Service `10130000` — undocumented

Not mentioned anywhere in the vendor web app and not referenced by anything this document
otherwise describes:

| Characteristic | Handles | Properties |
|---|---:|---|
| `10130001` … `1013000b` | 114–134 | read |
| `101300ff` | 136 | read, write, notify |

Eleven consecutive read-only characteristics and one read/write/notify at the top of the range.
No content has been read back and nothing is claimed about what the service is for. The shape
(a block of read-only values plus one control characteristic) is suggestive of a second
register bank, but that is not evidence — §7 item 8.

### 9.4 Services belonging to the BLE module

Also enumerated, and belonging to the module rather than the controller:

| Service | Characteristic | Properties |
|---|---|---|
| `00001801` | — | standard GATT service |
| `00000001-1989-0108-1234-123456789abc` | `00000003` | read, notify |
| | `00000002` | write-without-response, write |
| `01000002-1989-0108-1234-123456789abc` | `01000001` | write, notify |

Note a naming mismatch worth knowing about before anyone follows §6: the vendor app names
`00000002-1989-0108-1234-123456789abc` as the firmware-update **service**, but on this device
that UUID enumerates as a **characteristic** of service `00000001-1989-0108-1234-123456789abc`,
alongside a read/notify characteristic `00000003` — which is the write/notify pair a UART-style
telegram link needs. Whether §6's naming is shorthand or a mistake is not settled here; nothing
about the telegram protocol itself changes.

### 9.5 The write properties match the firmware's writable-bit whitelist

The firmware's telegram handler keeps a per-register whitelist of which bits a host is allowed
to set, and that list lines up exactly with which status characteristics advertise write
(STRONG):

| Register | Telegram | Writable bits in the firmware | Characteristic | Advertises write |
|---|---|---|---|:--:|
| PRJSTAT1 | `P` | 7, 8, 15 | `1010000c` | yes |
| PRJSTAT2 | `R` | 7, 8, 9, 10, 12 | `1010000d` | yes |
| PRJSTAT3 | `I` | 0, 10 | `1010000e` | yes |
| PRJSTAT4 | `M` | 12 | `1010000f` | yes |
| PRJSTAT5 | `K` | none | `10100010` | **no** |

Five registers, five matches, including the one negative case. That is strong evidence that
`1010000f` is PRJSTAT4 and `10100010` is PRJSTAT5 — the ordering assumed in §1 — and it is why
the properties are worth recording rather than treating as noise. It says nothing about whether
a write to any of them takes effect: PRJSTAT1 is on this list and §3.7 is what happened.

The telegram column is the `S`-group selector (§10.4). PRJSTAT5's `K` comes from the dispatcher
rather than from the whitelist, which is why it was blank here before.

---

## 10. Appendix — the controller's telegram command set

A full disassembly of the V01.03 image (`volcano_hybrid_1.3.bin`, Capstone, Thumb-2/M4)
recovered the controller's complete USART telegram command set. This is the layer *behind* the
GATT: the BLE module translates characteristic access into these telegrams (§1), so this command
set is the ceiling on what any characteristic can possibly do. Recording it explains why some
things are reachable over Bluetooth and others are not, and it is the reference for what must
never be written — **§10.7 is the safety-critical part of this appendix.**

The tags here follow the table at the head of this document without exception. **Nothing in this
appendix has been observed on a device**, so nothing in it is CONFIRMED: read straight off the
disassembled instruction stream at the address given is exactly what STRONG means here, however
little room for doubt an unambiguous opcode leaves. Addresses are cited throughout so each claim
can be re-checked, and reasoning *over* the image rather than reading it is marked SPECULATIVE.

### 10.1 Frame format (STRONG — image)

The framer `FUN_0800C4D8` validates a frame of the shape `FE <dst> <src> <len> … FD`. The
dispatcher then reads fixed fields out of it:

| Offset | Contents |
|---:|---|
| 0 | `FE`, start |
| 1 | destination |
| 2 | source |
| 3 | length |
| 4 | `'R'` (read) or `'W'` (write) |
| 5 | group letter |
| 6 | sub-index |
| 7 | sign / set digit — `'+'`, `'-'`, `'0'` or `'1'` |
| 8 … `len−2` | numeric payload |
| `0xa` … `0xd` | four ASCII-hex mask characters |
| last | `FD`, end |

Numeric write payloads are **ASCII decimal**, accumulated from offset 8 up to `len−2` as
`v = v * 10 + (c − '0')` (STRONG — image, at `0x0800CBD2`). Replies are an ASCII sign
followed by a zero-padded decimal.

The four mask characters overlap the numeric payload area. Which of the two a command reads is
decided by the command, not by the frame — a bit-mask command such as an `S W 'P'` register write
takes `[0xa..0xd]`, a scalar command such as `G Q` takes the decimal accumulator.

### 10.2 Two dispatchers, and the port difference (STRONG — image)

There are two dispatchers, one per port:

| Dispatcher | Port | Jump table |
|---|---|---|
| `FUN_0800A298` | wired USART1 | `0x0800A336` |
| `FUN_0800C5DC` | BLE USART3 | `0x0800C656` |

Both are `tbh` jump tables indexed by the group letter and both are **alphabetically ordered**.
Comparing the two tables gives the groups each port accepts:

| | Groups |
|---|---|
| Valid over **BLE** | `B C D E F G L M N O S T U V X Z` |
| **Wired only** — error stub on the BLE port | **`A`, `H`, `P`** |
| Error stub on both ports | `I J K Q R W Y` |

Stated plainly, because it closes off a question people ask: the **`H` group is live electrical
telemetry** — four `uint16` that look like voltage, current and power — and it is **not reachable
over Bluetooth at all**. Anyone hoping to get power metering out of this device over BLE should
stop here.

(§1 records the controller-to-module link as USART1. The two dispatchers put the module on
**USART3** and the wired service port on USART1; the earlier reading was of the wrong port.)

Note that a letter can appear at two levels without conflict: `I`, `K`, `P` and `R` are error
stubs as *group* letters, and the same letters are live *sub-indices* of the `S` group (§10.4).

### 10.3 The command groups (STRONG — image)

Offsets are into the config block at `0x20001658` or the status block at `0x20001E58` (the block
§8 identifies).

| Group | Sub-indices | What it does | Gate |
|---|---|---|---|
| `A` (wired only) | `' '`, `'8'`, `'9'` | keypad-test byte; operation counter | writes need 1989 / 815 |
| `B` | `' '`, `'1'`, `'9'` | three identity/serial strings, 18-byte ASCII | write needs 815 |
| `C` | — | control word; **payload `4711` enters the bootloader** | — |
| `D` | `' '`, `'1'`, `'9'` | packed date/version field (`+0x12`) | write needs 815 |
| `E` | `'0'`, `'5'` | reads an 8-byte record (`+0xC0` / `+0xC8`); **write zeroes the 16-byte block** | — |
| `F` | `'0'..'O'` | fault/history ring read, 80 × `uint16` from `+0x20` | **write clears the ring**, needs 1989 |
| `G` | numerics and letters | pump, timers and the PID block — see §10.5 | mixed |
| `H` (wired only) | `'0'`, `'1'`, `'9'` | live electrical telemetry, 4 × `uint16` | — |
| `L` | `'P'`, `'S'` | LED brightness (`cfg+0x42`, 0–100); a 16-bit setting | — |
| `M`, `N` | `'0'`, `'1'` | 64-bit statistics records (`+0xd0`, `+0xd4`) | write needs 1989 |
| `O` | many | lifetime hour/minute counters (`+0xe4…+0xf4`), setpoints | writes need 815 or 1989 |
| `P` (wired only) | `'G'`, `'0/1/2'`, `'C'`, … | serial record in flash; **`'C'` with payload 9000 programs FLASH** | passcode |
| `S` | `'A'..'X'` | the status-word group — see §10.4 | mixed |
| `T` | `'T/a/b/A/B/D/I/K/R/S/d/r/s/t'` | temperature and **temperature-sensor calibration** | write needs 1989 |
| `U` | `'U'` | **ADC / temperature gain calibration** (`+0x18` slope) | needs 1989 |
| `V` | `'0/1/3/4/5/A/B'` | version and identity strings, including the radio-module id | write needs 815 |
| `X` | `' '`, `'1'`, `'A'`, `'B'` | 40-character and identity strings | write needs 815 |
| `Z` | `'a'..'e'` | five 32-bit statistics (`+0x7c…+0x84`) | write needs 815 |

### 10.4 The `S` group in detail (STRONG — image)

`S` is the status-word group: the telegrams behind the PRJSTAT characteristics, and rather more
besides.

- Reads `'A'..'X'` return the five PRJSTAT words, the model class, and service words.
- **`S W '0'` with payload 1989 → immediate CPU reset** (SCB `AIRCR` = `0x05FA0004`, at
  `0x0800B338` / `0x0800D1A4`).
- `S W '1'..'5'` set pending-work bits 0–5 at `0x200000CA`. **`'5'` with payload 1000 restores
  factory defaults** — `FUN_080012AE` rewrites the config block and wipes the counters.
- `S W 'P'/'R'/'I'/'M'/'K'` are the PRJSTAT1/2/3/4/5 bit writes, each against the per-register
  whitelist already recorded in §9.5. This confirms the selector→word map, including
  **`'K'` → PRJSTAT5 at `+0x1c`**, which §9.5 could not name.
- `S W 'q/r/s/t/u/v/x/y'` are direct heat / air / **second-stage** on-off and burn-in
  enter/leave, gated on actuator state.

### 10.5 `G Q` and `G R` — pump percent and pump step (STRONG — image)

- **`G Q` (`0x51`)** reads and writes **config `+0x40`, the pump power percent**, factory default
  100. The payload is ASCII decimal **0–100**; anything above 100 is rejected with error 8. It is
  **ungated** — no passcode, no actuator interlock. The value reads back via `G R Q`. A write also
  sets the config-changed notify word at `0x2000012C` and flags a pending config-flash save.
  Write site `0x0800CC92` (`cmp #0x64; bhi`), read site `0x0800CBC0`.
- **`G R` (`0x52`)** is the direct pump step, writing `0x2000016a` plus a mode byte chosen by band
  (`0x33` / `0x4b` / `0x64`). It is **gated on PRJSTAT1 bit 12 AND bit 15**; with either clear it
  returns error 3 and does nothing.
- `FUN_08008B28` (at `0x08008B52`) selects `cfg+0x40` as the pump source **only while PRJSTAT1
  bit 15 is clear**. So `G Q`'s value drives the pump in normal mode, and the step value wins in
  air step mode (§3.1, bit 15).

Both are valid entries in the **BLE** dispatch table, so both are reachable over Bluetooth *if*
the module binds a characteristic to them.

### 10.6 Why the pump-percent route is nevertheless blocked

A negative result, recorded so the next person does not spend the same time on it.

- **The characteristic→telegram binding lives in the radio module's firmware, which is not in
  this image.** Nothing in the controller image assigns a GATT handle to any command. The binding
  can be reasoned about; it cannot be derived from this dump. CONFIRMED (image, as an absence).
- The tempting inference — that the module's characteristic map is an order-preserving projection
  of the command set, given that `1010000c…10` are PRJSTAT1…5 with write properties matching the
  whitelists five for five (§9.5) — **does not hold as a general rule.** Those five are one
  contiguous native array walked in index order, and their selector letters `P, R, I, M, K` are
  not alphabetical, not dispatch order and not config-offset order. Checked against the known
  `10110000` bindings, five different groups appear interleaved by function, and `03`
  (`cfg+0x44`) precedes `05` (`cfg+0x42`), so it is not offset-ordered either. The map is
  hand-curated. STRONG.
- Evidence that pump power may not be exposed at all: `cfg+0x40` defaults to 100, **no
  characteristic in the observed dump reads 100**, and `10110004` read `0` both idle and with the
  pump running at full speed. A characteristic mirroring `cfg+0x40` should read 100 on a
  factory-default unit. STRONG.
- `10110004` remains the best positional candidate if one exists at all — a writable notify scalar
  sitting between `03` (`cfg+0x44`) and `05` (`cfg+0x42`), exactly where `cfg+0x40` would belong —
  but its read value contradicts that. SPECULATIVE, and explicitly not to be acted on.

### 10.7 Commands that must never be written blind

**Never write a characteristic whose binding is unknown, and never sweep writable
characteristics.** The reason is this list: every one of these commands sits in the same command
set as the harmless ones, behind bindings nobody outside Storz & Bickel has enumerated. Every
entry STRONG (image).

| Command | What it does |
|---|---|
| `C` + 4711 | **Bootloader entry** — mirrored at GATT `10100011` (§6) |
| `S W '0'` + 1989 | **Immediate CPU reset** |
| `S W '5'` + 1000 | **Factory defaults restored** — config block rewritten, counters wiped |
| `P W 'C'` + 9000 | **FLASH programming** |
| `T W` / `U W` + 1989 | **Temperature-sensor and ADC calibration overwrite** — silent, and every temperature reading is wrong afterwards |
| `B` / `D` / `V` / `X` + 815 | **Serial number, article number, date and radio-module identity overwrite** |
| `F W`, `E W '0'` | **Fault-ring clear and statistics-block zeroing** — the history in §3.5 is destroyed |
| `S W 'P/R/I/M/K'`, `S W 'q/r/…'` | **Direct actuator forcing** — can leave the heater on |

The passcodes are the tell. **815 (`0x32f`)** and **1989 (`0x7c5`)**, plus the special payloads
**1000**, **4711** and **9000**: their presence in a write means the command touches identity,
calibration, flash, DFU or reset. Nothing in normal operation needs any of them.

Two of these are already reachable over the GATT this document describes — `10100011` is the
`C` + 4711 bootloader unlock (§6), and §3.7 is what a single well-meant write to an advertised
writable status register actually did.
