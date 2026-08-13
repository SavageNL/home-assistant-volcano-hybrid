# Changelog

All notable changes to this integration are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `Unreleased` section below becomes the release notes of the next tag that
is pushed, so add entries to it as changes land and write them for the people
installing the integration rather than for the commit log. There is no version
to set. See [CONTRIBUTING.md](CONTRIBUTING.md#the-changelog).

This file starts at 1.0.4. Releases up to and including 1.0.3 are only on the
[GitHub releases page](https://github.com/SavageNL/home-assistant-volcano-hybrid/releases).

## [Unreleased]

### Added

- A **Ready** binary sensor, on once the vaporizer reports it reached the target
  temperature. This is the device's own signal rather than a comparison of the
  current temperature against the target — the same one that drives its
  vibration alert, so it turns on exactly when the Volcano says it is ready. It
  follows the device's own idea of "reached", which means a target change of
  2 °C or less does not turn it off, and it stays on while the device cools
  down.
- The thermostat card now shows **Heating** while the vaporizer is working
  towards its target, **Heat** once it is holding temperature, and **Idle**
  while it cools down with its display still lit after being switched off.
- Diagnostic entities for the decoded device status, all disabled by default:
  **Heater running**, **Pump running** and a **Heater/pump fault** sensor that
  turns on when the vaporizer reports a timing fault in its heater control,
  which stops both the heater and the pump.
- Three more diagnostic binary sensors, also disabled by default: **Service
  mode**, on while the vaporizer is running the burn-in mode that heats it to
  230 °C for ten minutes on its own; **Air step mode**, on when the AIR button
  steps the pump through 100/75/50 % instead of toggling it; and **Second
  temperature stage**, on when the vaporizer adds its boost offset to the
  target.
- Diagnostic sensors for the raw **status registers 1/2/3** and **error history
  1/2**, reported as hex, also disabled by default. They carry the bits this
  integration does not interpret, which is what makes them worth reading when a
  fault has to be diagnosed. **Status registers 4 and 5** are read too: they are
  the vaporizer's two remaining status words, which nothing decodes yet and
  which stay empty on a device that does not report them.
- A **Mains voltage** diagnostic sensor, disabled by default, showing the mains
  the vaporizer reports it was built for (`230VAC`). The model on the device
  page now comes from the vaporizer itself instead of being assumed — it still
  reads *Volcano Hybrid*, but it is now the device saying so.
- [`VOLCANO_BLE_SPEC.md`](VOLCANO_BLE_SPEC.md): a full description of the
  Volcano Hybrid's Bluetooth protocol — every characteristic, how its value is
  encoded, what each status-register bit means, and the firmware-update
  protocol this integration deliberately does not implement.

### Fixed

- The **Error history 1/2** sensors showed a double-encoded value. The
  vaporizer already sends its fault log as text, and the integration encoded
  that text a second time, so a log reading `6161616161617261` was shown as
  `36313631363136313631363137323631`. It now shows exactly what the device
  reports.

## [1.0.4] - 2026-08-01

### Added

- An **Auto connect** switch. Turning it off releases the vaporizer so other
  Bluetooth clients (such as the official app) can reach it; commands and the
  reconnect buttons still connect on demand.
- A **(Re)connect after delay** button that stays disconnected long enough for
  the vaporizer to advertise again, so a better Bluetooth path can be picked.
- Options to tune the auto-connect and delayed-reconnect delays.
- A reconfigure flow, so an entry can be pointed at a different vaporizer
  without deleting and re-adding it.
- Downloadable diagnostics for bug reports, with the Bluetooth address and
  serial number redacted. They include the vaporizer's raw status registers
  and error history — the same values the official app's **Analysis** button
  collects for Storz & Bickel support.
- A **Firmware** update entity, reporting whether the vaporizer is running the
  newest firmware this release knows about (currently V01.03). Installing it
  still means using the official web app, so the entity links there rather than
  offering a button. Home Assistant never contacts Storz & Bickel: the version
  is recorded in the integration and refreshed by its maintainers.
- Icons for the entities that do not get one from their device class.

### Fixed

- The periodic update stopped running a few minutes after every connect, which
  is why the current temperature could still freeze on a stale reading. The
  vaporizer stops advertising once something is connected to it, so Home
  Assistant drops it from its Bluetooth address cache, and the update skipped
  itself whenever that lookup came up empty — silently, while the integration
  still showed as connected. It now refreshes over the connection it already
  has. This also restores replaying a command the vaporizer missed.
- The current temperature could stay stuck on an old reading indefinitely. It
  was read only once when connecting and then left entirely to Bluetooth
  notifications, so a single dropped notification was never corrected. The
  periodic update now re-reads it.
- Connecting could hang forever if a command was still pending, leaving the
  integration wedged until Home Assistant was restarted.
- Home Assistant startup no longer waits for the vaporizer. The first connect
  runs in the background, so a device that is off or out of range at boot does
  not delay startup.
- Reconnecting after the vaporizer was powered on leaked Bluetooth connection
  slots until Home Assistant was restarted.
- The climate entity reported 0 °C current, 40 °C target and "off" before it had
  read anything from the vaporizer, and those invented values were stored in the
  recorder as though they were readings. It now reports unknown until the real
  state is known.
- The signal strength sensor now follows advertisements instead of only
  updating on the periodic poll.
- Bluetooth discovery no longer errors on an advertisement that carries no
  name, which it could hit while checking any nearby device.
