# Changelog

All notable changes to this integration are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `Unreleased` section below becomes the release notes of the next tag that
is pushed, so add entries to it as changes land and write them for the people
installing the integration rather than for the commit log. There is no version
to set. See [CONTRIBUTING.md](CONTRIBUTING.md#the-changelog).

This file starts at 1.0.3. Earlier releases are only on the
[GitHub releases page](https://github.com/SavageNL/home-assistant-volcano-hybrid/releases).

## [Unreleased]

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
  serial number redacted.
- A complete example dashboard in the README, with a screenshot.
- Icons for the entities that do not get one from their device class.

### Fixed

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

### Changed

- The integration now documents itself against the Home Assistant
  quality scale at **platinum**, including full typing and translated error
  messages.
