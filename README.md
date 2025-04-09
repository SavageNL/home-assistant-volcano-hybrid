# Home Assistant Volcano Hybrid

A Storz & Bickel Volcano Hybrid integration for Home Assistant

## Installing

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

Install using HACS, or download the repository and put the files from `custom-components` in your `config/custom_components` folder.

## Quick start

- Add the integration
- Power on your Volcano Hybrid
- If you have BLE adapters configured the device should be discovered automatically


## Usage

This integration adds a `climate` entity to control the Volcano Hybrid:

It shows the following information and allows these controls:
- Current temperature
- Target temperature
- Set directly or increase value in 1 degree steps
- Enable/disable heating
- Enable/disable fan

![Climate entity](resources/climate_entity.png)

Additionally there are the following configuration/diagnostic entities:
- The auto off time setting (configurable)
- Led brightness (configurable)
- Whether the device is showing temperature in celsius or fahrenheit (configurable)
- Whether vibration is enabled (configurable)
- The total heating time
- Whether the auto off timer is enabled (this is essentially the same as the heating state)

## Notice

This integration will connect to the Volcano as soon as it finds one (after it has been setup). 
This means that updates from the device will trigger updates in Home Assistant instantly, but also that no other bluetooth devices will be able to control the Volcano.

I'm planning to make that configurable at some point.
