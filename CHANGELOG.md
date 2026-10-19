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

- Support for the Crafty and Crafty+ (experimental — decoded from the vendor
  web app and untested on hardware; see `CRAFTY_BLE_SPEC.md`).
- Support for the Venty and Veazy (experimental — untested on hardware; see
  `VENTY_BLE_SPEC.md`). These devices are polled once a second while connected.
- The integration is now titled "Storz & Bickel"; the domain and every
  existing entity id are unchanged.
- An [examples site](https://savagenl.github.io/home-assistant-volcano-hybrid/)
  replaces the examples in the README. Fill a bag, the temperature
  progression, and the new hands-free bag session, whip session and party
  rounds (thanks @magikh0e) can be imported as blueprints.
- The brand icon is now bundled with the integration
  (`custom_components/volcano_hybrid/brand/icon.png`), so HACS no longer needs
  to reach the Home Assistant brands server to validate the repository.

### Changed

- Config entries record the device family (`model`); existing entries are
  migrated as Volcano Hybrids automatically, and rolling back to 1.0.5 still
  loads them.
- The Volcano's **Auto-off time** now starts at 30 minutes, like the official
  app; it no longer offers 0. A device already set below 30 minutes keeps its
  setting until you change it.
- The Volcano's target temperature is now written in the same 4-byte form the
  official app uses.
- The weekly firmware check tracks each family separately, so its issues are
  now labelled per family (`firmware-watch:volcano_hybrid-outdated`,
  `firmware-watch:venty-endpoint-error`, …) rather than per kind of problem
  alone.

### Fixed

- After another Bluetooth client (such as the official web app) had connected
  to the vaporizer, the integration could come up with an incomplete list of the
  device's Bluetooth services and fail with "Characteristic … not found" on
  every update until Home Assistant restarted. It now drops that cached list
  and reconnects, discovering the services again.
- A device whose first read after connecting failed stayed connected with half
  its state unknown, and nothing ever reconnected it to read the rest. Such a
  connect is now dropped and retried.
- A Bluetooth link that dropped while a connect was still reading the device,
  just as a command waiting to be resent went out, wedged the connection: the
  device never reconnected until Home Assistant restarted.
- Unloading or reloading the integration could leave a Bluetooth connection
  behind: a connect already under way kept running, and an update after unload
  could still reconnect. Both now stop with the integration.
- **Current on time** could go negative after the auto-off time was lowered
  mid-session. It now shows as unknown until the vaporizer next switches on.

## [1.0.5] - 2026-08-19

### Added

- A **Ready** binary sensor, on once the vaporizer reports it reached the target
  temperature. This is the device's own signal rather than a comparison of the
  current temperature against the target — the same one that drives its
  vibration alert, so it turns on exactly when the Volcano says it is ready. It
  follows the device's own idea of "reached": it turns off again only when the
  target is raised at least 3 °C above the previous one, never when the target
  is lowered, and it stays on while the device cools down.
- The thermostat card now shows **Heating** while the vaporizer is working
  towards its target, **Heat** once it is holding temperature, and **Idle**
  while it cools down with its display still lit after being switched off.
- Diagnostic entities for the decoded device status, all disabled by default:
  **Heater running**, **Pump running** and a **Heater/pump fault** sensor that
  turns on when the vaporizer reports a timing fault in its heater control,
  which stops both the heater and the pump.
- A **Service mode** binary sensor, also disabled by default, on while the
  vaporizer is running the burn-in mode that heats it to 230 °C for ten minutes
  on its own. Holding HEAT and AIR together for a few seconds starts it, so it
  is worth being told about if it happens by accident.
- Diagnostic sensors for the raw **status registers 1/2/3** and **error history
  1/2**, reported as hex, also disabled by default. They carry the bits this
  integration does not interpret, which is what makes them worth reading when a
  fault has to be diagnosed. **Status registers 4 and 5** are read too: they are
  the vaporizer's two remaining status words, which nothing decodes yet and
  which stay empty on a device that does not report them.
- A **Last fault** diagnostic sensor, disabled by default, naming the newest
  fault the vaporizer logged instead of leaving it as digits to look up — a
  temperature sensor fault, a heater feedback problem, and so on. Its
  attributes hold the rest of the log, decoded and raw, which is what to attach
  to a bug report. A code the integration does not recognise is reported as
  *Unrecognised fault code* with the code itself kept in the attributes, rather
  than being guessed at.
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
